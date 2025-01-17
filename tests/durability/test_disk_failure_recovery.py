#!/usr/bin/python # pylint: disable=C0302
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Seagate Technology LLC and/or its Affiliates
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# For any questions about this software or licensing,
# please email opensource@seagate.com or cortx-questions@seagate.com.

"""
Test suite for disk failure recovery
"""

import logging
import time
import random
import pytest

from commons.helpers.health_helper import Health
from commons.helpers.pods_helper import LogicalNode
from commons.utils import assert_utils
from commons import constants as common_const
from config import CMN_CFG
from libs.di.di_mgmt_ops import ManagementOPs
from libs.ha.ha_common_libs_k8s import HAK8s
from libs.durability.durability_disk_failure_recovery_libs import DiskFailureRecoveryLib

# Global Constants
LOGGER = logging.getLogger(__name__)


class TestDiskFailureRecovery:
    """
    Test suite for disk failure recovery
    """

    @classmethod
    def setup_class(cls):
        """
        Setup operations for the test file.
        """
        LOGGER.info("STARTED: Setup Module operations.")
        cls.num_nodes = len(CMN_CFG["nodes"])
        cls.username = []
        cls.password = []
        cls.test_prefix = []
        cls.failed_disks = []
        cls.node_master_list = []
        cls.hlth_master_list = []
        cls.node_worker_list = []
        cls.ha_obj = HAK8s()
        cls.dsk_rec_obj = DiskFailureRecoveryLib()
        cls.s3_clean = None
        cls.parity_units = None
        cls.mgnt_ops = ManagementOPs()
        cls.delay_sns_repair = 30

        for node in range(cls.num_nodes):
            cls.host = CMN_CFG["nodes"][node]["hostname"]
            user_name = CMN_CFG["nodes"][node]["username"]
            user_pass = CMN_CFG["nodes"][node]["password"]
            if CMN_CFG["nodes"][node]["node_type"] == "master":
                cls.node_master_list.append(LogicalNode(hostname=cls.host,
                                                        username=user_name,
                                                        password=user_pass))
                cls.hlth_master_list.append(Health(hostname=cls.host,
                                                   username=user_name,
                                                   password=user_pass))
            else:
                cls.node_worker_list.append(LogicalNode(hostname=cls.host,
                                                        username=user_name,
                                                        password=user_pass))

    def setup_method(self):
        """
        This function will be invoked prior to each test case.
        """
        LOGGER.info("STARTED: Setup Operations")
        self.s3_clean = {}
        LOGGER.info("Check the overall status of the cluster.")
        resp = self.ha_obj.check_cluster_status(self.node_master_list[0])
        if not resp[0]:
            resp = self.ha_obj.restart_cluster(self.node_master_list[0])
            assert_utils.assert_true(resp[0], resp[1])
        LOGGER.info("Cluster status is online.")

        LOGGER.info("Getting parity units count.")
        resp = self.dsk_rec_obj.retrieve_durability_values(self.node_master_list[0], "sns")
        assert_utils.assert_true(resp[0], resp[1])
        self.parity_units = resp[1]['parity']
        LOGGER.info("Done: Setup operations.")

    def teardown_method(self):
        """
        This function will be invoked after each test function in the module.
        """
        LOGGER.info("STARTED: Teardown Operations.")
        LOGGER.info("Cleanup: Make failed disks online")
        resp = self.node_master_list[0].get_pod_name(pod_prefix=common_const.POD_NAME_PREFIX)
        assert_utils.assert_true(resp[0], resp[1])
        pod_name = resp[1]
        for select_disk in self.failed_disks:
            fail_disk = select_disk.split('$')
            resp = self.dsk_rec_obj.change_disk_status_hctl(self.node_master_list[0], pod_name,
                                                            fail_disk[0], fail_disk[2], "online")
            LOGGER.info("disk status change resp: %s", resp)
        LOGGER.info("Cleanup: Made all disks online")

        if self.s3_clean:
            LOGGER.info("Cleanup: Cleaning created s3 accounts and buckets.")
            resp = self.ha_obj.delete_s3_acc_buckets_objects(self.s3_clean)
            assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Cleanup: Check cluster status")
        resp = self.ha_obj.check_cluster_status(self.node_master_list[0])
        assert_utils.assert_true(resp[0], resp[1])
        LOGGER.info("Cleanup: Cluster status checked successfully")
        LOGGER.info("Done: Teardown completed.")

    # pylint: disable=too-many-statements
    @pytest.mark.lc
    @pytest.mark.tags("TEST-36580")
    def test_sns_repair_fail_disk_less_than_k(self):
        """
        Validate SNS repair works fine with failed disks are less than K(parity units)
        """
        LOGGER.info("STARTED: Validate SNS repair works fine with failed disks "
                    "are less than K(parity units)")

        LOGGER.info("Step 1: Do IOs(Write and Read)")
        users = self.mgnt_ops.create_account_users(nusers=1)
        self.test_prefix.append('test-36580')
        self.s3_clean = users
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 2: Get degraded byte count before failing the disk")
        degraded_byte_cnt_before = self.dsk_rec_obj.get_byte_count_hctl(self.hlth_master_list[0],
                                                                        "degraded_byte_count")
        LOGGER.info("degraded byte count: %s", degraded_byte_cnt_before)

        LOGGER.info("Step 3: Fail disks less than K(parity units)")
        LOGGER.info("No of parity units (K): %s", self.parity_units)

        if self.parity_units == 1:
            disk_fail_cnt = 1
        else:
            disk_fail_cnt = random.randint(1, self.parity_units-1)  # nosec
        LOGGER.info("No of disks to be failed: %s", disk_fail_cnt)

        resp = self.dsk_rec_obj.get_all_nodes_disks(self.node_master_list[0],
                                                    self.node_worker_list)
        assert_utils.assert_true(resp[0], resp[1])
        all_disks = resp[1]
        LOGGER.info("list of all disks: %s", all_disks)

        resp = self.node_master_list[0].get_pod_name(pod_prefix=common_const.POD_NAME_PREFIX)
        assert_utils.assert_true(resp[0], resp[1])
        pod_name = resp[1]

        for cnt in range(disk_fail_cnt):
            selected_disk = random.choice(all_disks)  # nosec
            fail_disk = selected_disk.split('$')
            LOGGER.info("disk fail loop: %s, disk selected for failure: %s", cnt + 1, fail_disk)
            resp = self.dsk_rec_obj.change_disk_status_hctl(self.node_master_list[0], pod_name,
                                                            fail_disk[0], fail_disk[2], "failed")
            LOGGER.info("fail disk resp: %s", resp)
            self.failed_disks.append(selected_disk)

        time.sleep(self.delay_sns_repair)
        LOGGER.info("Step 4: Get degraded byte count after disk failure")
        degraded_byte_cnt_after_fail = self.dsk_rec_obj.get_byte_count_hctl\
            (self.hlth_master_list[0], "degraded_byte_count")
        LOGGER.info("degraded byte cunt: %s", degraded_byte_cnt_after_fail)

        if degraded_byte_cnt_before >= degraded_byte_cnt_after_fail:
            assert_utils.assert_true(False, "Degraded byte count after disk failure less than "
                                            "or equal to degraded byte count before disk fail")
        else:
            LOGGER.info("Degraded byte count is more as expected after disk fail")

        LOGGER.info("Step 5: Do IOs(Write and Read) after disk failure")
        self.test_prefix.append('test-36580-after-disk-fail')
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 6: Check cluster status")
        resp = self.hlth_master_list[0].all_cluster_services_online()
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 7: Start SNS repair")
        resp = self.dsk_rec_obj.sns_repair(self.node_master_list[0], "start", pod_name)
        LOGGER.info("sns start resp: %s", resp)

        time.sleep(self.delay_sns_repair)
        LOGGER.info("Step 8: Check degraded byte counts are zero "
                    "or less than count after disk fail")
        degraded_byte_cnt_after_repair = self.dsk_rec_obj.get_byte_count_hctl\
            (self.hlth_master_list[0], "degraded_byte_count")
        LOGGER.info("degraded byte cunt: %s", degraded_byte_cnt_after_repair)

        if degraded_byte_cnt_after_repair >= degraded_byte_cnt_after_fail:
            assert_utils.assert_true(False, "Degraded byte count after disk failure less than "
                                            "or equal to degraded byte count before disk fail")
        else:
            LOGGER.info("Degraded byte count after sns repair is less than "
                        "degraded byte count after disk fail")

        LOGGER.info("Step 9: Check cluster status after repair")
        resp = self.hlth_master_list[0].all_cluster_services_online()
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 10: Read data written in step 1")
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[0],
                                                    skipwrite=True,
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 11: Do IOs(Write and Read)")
        self.test_prefix.append('test-36580-after-recovery')
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("COMPLETED: Test SNS repair works fine with failed disks "
                    "are less than K(parity units)")

    # pylint: disable=too-many-statements
    @pytest.mark.lc
    @pytest.mark.tags("TEST-36581")
    def test_sns_repair_fail_disk_equal_to_k(self):
        """
        Validate SNS repair works fine with failed disks are equal to K(parity units)
        """
        LOGGER.info("STARTED: Validate SNS repair works fine with failed disks "
                    "are equal to K(parity units)")

        LOGGER.info("Step 1: Do IOs(Write and Read)")
        users = self.mgnt_ops.create_account_users(nusers=1)
        self.test_prefix.append('test-36581')
        self.s3_clean = users
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 2: Get degraded byte count before failing the disk")
        degraded_byte_cnt_before = self.dsk_rec_obj.get_byte_count_hctl(self.hlth_master_list[0],
                                                                        "degraded_byte_count")
        LOGGER.info("degraded byte cunt: %s", degraded_byte_cnt_before)

        LOGGER.info("Step 3: Fail disks less than K(parity units)")
        LOGGER.info("No of parity units (K): %s", self.parity_units)

        disk_fail_cnt = self.parity_units
        LOGGER.info("No of disks to be failed: %s", disk_fail_cnt)

        resp = self.dsk_rec_obj.get_all_nodes_disks(self.node_master_list[0],
                                                    self.node_worker_list)
        assert_utils.assert_true(resp[0], resp[1])
        all_disks = resp[1]
        LOGGER.info("list of all disks: %s", all_disks)

        resp = self.node_master_list[0].get_pod_name(pod_prefix=common_const.POD_NAME_PREFIX)
        assert_utils.assert_true(resp[0], resp[1])
        pod_name = resp[1]

        for cnt in range(disk_fail_cnt):
            selected_disk = random.choice(all_disks)  # nosec
            fail_disk = selected_disk.split('$')
            LOGGER.info("disk fail loop: %s, disk selected for failure: %s", cnt + 1, fail_disk)
            resp = self.dsk_rec_obj.change_disk_status_hctl(self.node_master_list[0], pod_name,
                                                            fail_disk[0], fail_disk[2], "failed")
            LOGGER.info("fail disk resp: %s", resp)
            self.failed_disks.append(selected_disk)

        time.sleep(self.delay_sns_repair)
        LOGGER.info("Step 4: Get degraded byte count after disk failure")
        degraded_byte_cnt_after_fail = self.dsk_rec_obj.get_byte_count_hctl\
            (self.hlth_master_list[0], "degraded_byte_count")
        LOGGER.info("degraded byte cunt: %s", degraded_byte_cnt_after_fail)

        if degraded_byte_cnt_before >= degraded_byte_cnt_after_fail:
            assert_utils.assert_true(False, "Degraded byte count after disk failure less than "
                                            "or equal to degraded byte count before disk fail")
        else:
            LOGGER.info("Degraded byte count is more as expected after disk fail")

        LOGGER.info("Step 5: Do IOs(Write and Read) after disk failure")
        self.test_prefix.append('test-36581-after-disk-fail')
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 6: Check cluster status")
        resp = self.hlth_master_list[0].all_cluster_services_online()
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 7: Start SNS repair")
        resp = self.dsk_rec_obj.sns_repair(self.node_master_list[0], "start", pod_name)
        LOGGER.info("sns start resp: %s", resp)

        time.sleep(self.delay_sns_repair)
        LOGGER.info("Step 8: Check degraded byte counts are zero "
                    "or less than count after disk fail")
        degraded_byte_cnt_after_repair = self.dsk_rec_obj.get_byte_count_hctl\
            (self.hlth_master_list[0], "degraded_byte_count")
        LOGGER.info("degraded byte cunt: %s", degraded_byte_cnt_after_repair)

        if degraded_byte_cnt_after_repair >= degraded_byte_cnt_after_fail:
            assert_utils.assert_true(False, "Degraded byte count after sns repair is greater than "
                                            "or equal to degraded byte count after disk fail")
        else:
            LOGGER.info("Degraded byte count after sns repair is less than "
                        "degraded byte count after disk fail")

        LOGGER.info("Step 9: Check cluster status after repair")
        resp = self.hlth_master_list[0].all_cluster_services_online()
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 10: Read data written in step 1")
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[0],
                                                    skipwrite=True,
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("Step 11: Do IOs(Write and Read)")
        self.test_prefix.append('test-36581-after-recovery')
        resp = self.ha_obj.ha_s3_workload_operation(s3userinfo=list(users.values())[0],
                                                    log_prefix=self.test_prefix[-1],
                                                    skipcleanup=True)
        assert_utils.assert_true(resp[0], resp[1])

        LOGGER.info("COMPLETED: Test SNS repair works fine with failed disks "
                    "are equal to K(parity units)")
