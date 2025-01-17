#!/usr/bin/python
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
#
"""Tests various operations on IAM users using REST API
NOTE: These tests are no longer valid as CSM will no longer support IAM user operations.
"""
import logging
import time
from http import HTTPStatus
import os
from random import SystemRandom
import pytest

from commons import configmanager
from commons import cortxlogging
from commons import commands as common_cmd
from commons.constants import Rest as const
from commons.params import TEST_DATA_FOLDER
from commons.utils import assert_utils
from commons.utils import system_utils
from config import CSM_REST_CFG
from libs.csm.csm_interface import csm_api_factory
from libs.csm.csm_setup import CSMConfigsCheck
from libs.csm.rest.csm_rest_iamuser import RestIamUser
from libs.s3.s3_test_lib import S3TestLib


class TestIamUser():
    """REST API Test cases for IAM users"""

    @classmethod
    def setup_class(cls):
        """
        This function will be invoked prior to each test case.
        It will perform all prerequisite test steps if any.
        """
        cls.log = logging.getLogger(__name__)
        cls.log.info("Initializing test setups")
        cls.csm_conf = configmanager.get_config_wrapper(fpath="config/csm/test_rest_iam_user.yaml")
        cls.log.info("Ended test module setups")
        cls.config = CSMConfigsCheck()
        setup_ready = cls.config.check_predefined_s3account_present()
        if not setup_ready:
            setup_ready = cls.config.setup_csm_s3()
        assert setup_ready
        cls.created_iam_users = set()
        cls.rest_iam_user = RestIamUser()
        cls.log.info("Initiating Rest Client ...")

    def teardown_method(self):
        """Teardown method which run after each function.
        """
        self.log.info("Teardown started")
        for user in self.created_iam_users:
            self.rest_iam_user.delete_iam_user(
                login_as="s3account_user", user=user)
        self.log.info("Teardown ended")

    @pytest.mark.skip(reason="EOS-22292: CSM APIs which requires S3 Account login are unsupported")
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-10732')
    def test_1133(self):
        """Test that IAM users are not permitted to login
          """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        status_code = self.csm_conf["test_1133"]
        status, response = self.rest_iam_user.create_and_verify_iam_user_response_code()
        assert status, response
        user_name = response['user_name']
        self.created_iam_users.add(response['user_name'])
        assert (
                self.rest_iam_user.iam_user_login(user=user_name) == status_code["status_code"])
        self.log.info("##### Test ended -  %s #####", test_case_name)

    @pytest.mark.skip(reason="EOS-22292: CSM APIs which requires S3 Account login are unsupported")
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-14749')
    def test_1041(self):
        """Test that S3 account should have access to create IAM user from back end
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)

        self.log.info("Creating IAM user")
        status, response = self.rest_iam_user.create_and_verify_iam_user_response_code()
        print(status)
        self.log.info(
            "Verifying status code returned is 200 and response is not null")
        assert status, response

        for key, value in response.items():
            self.log.info("Verifying %s is not empty", key)
            assert value

        self.log.info("Verified that S3 account %s was successfully able to create IAM user: %s",
                      self.rest_iam_user.config["s3account_user"]["username"], response)

        self.log.info("##### Test ended -  %s #####", test_case_name)

    @pytest.mark.skip("Test invalid for R2")
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-17189')
    def test_1022(self):
        """
        Test that IAM user is not able to execute and access the CSM REST APIs.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)

        self.log.debug(
            "Verifying that IAM user is not able to execute and access the CSM REST APIs")
        assert self.rest_iam_user.verify_unauthorized_access_to_csm_user_api()
        self.log.debug(
            "Verified that IAM user is not able to execute and access the CSM REST APIs")
        self.log.info("##### Test ended -  %s #####", test_case_name)


class TestIamUserRGW():
    """
    Tests related to RGW
    """

    @classmethod
    def setup_class(cls):
        """
        setup class
        """
        cls.log = logging.getLogger(__name__)
        cls.log.info("[START] CSM setup class started.")
        cls.log.info("Initializing test configuration...")
        cls.csm_obj = csm_api_factory("rest")
        cls.csm_conf = configmanager.get_config_wrapper(fpath="config/csm/test_rest_iam_user.yaml")
        cls.rest_resp_conf = configmanager.get_config_wrapper(
            fpath="config/csm/rest_response_data.yaml")
        cls.config = CSMConfigsCheck()
        setup_ready = cls.config.check_predefined_csm_user_present()
        if not setup_ready:
            setup_ready = cls.config.setup_csm_users()
        assert setup_ready
        cls.created_iam_users = set()
        cls.cryptogen = SystemRandom()
        cls.file_size = cls.cryptogen.randrange(10, 100)
        cls.log.info("[END] CSM setup class completed.")

    def teardown_method(self):
        """Teardown method which run after each function.
        """
        self.log.info("Teardown started")
        delete_failed = []
        delete_success = []
        for user in self.created_iam_users:
            self.log.info("deleting iam user %s", user)
            resp = self.csm_obj.delete_iam_user(user=user, purge_data=True)
            self.log.debug("Verify Response : %s", resp)
            if resp.status_code != HTTPStatus.OK:
                delete_failed.append(user)
            else:
                delete_success.append(user)
        for usr in delete_success:
            self.created_iam_users.remove(usr)
        self.log.info("IAM delete success list %s", delete_success)
        self.log.info("IAM delete failed list %s", delete_failed)
        assert len(delete_failed) == 0, "Delete failed for IAM users"
        self.log.info("Teardown ended")

    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35603')
    def test_35603(self):
        """
        Test create IAM User with Invalid uid and display-name parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Testing with empty UID")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload["uid"] = ""
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, "Status code check failed for empty uid"
        self.log.info("[END] Testing with empty UID")

        self.log.info("[START] Testing with empty display name")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload["display_name"] = ""
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status code check failed for empty display name"
        self.log.info("[END] Testing with empty display name")

        self.log.info("[START] Testing with empty UID and display name")
        payload = {"uid": "", "display_name": ""}
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status code check failed for empty uid and display name"
        self.log.info("[END] Testing with empty UID and display name")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35604')
    def test_35604(self):
        """
        Test create IAM User with missing uid and display-name parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Testing with missing UID")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="loaded")
        payload.pop("uid")
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, "Status check failed for missing uid"
        self.log.info("[END] Testing with missing UID")

        self.log.info("[START] Testing with missing display name")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="loaded")
        payload.pop("display_name")
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status code check failed for missing display name"
        self.log.info("[END] Testing with missing display name")

        self.log.info("[START] Testing with missing UID and display name")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="loaded")
        payload.pop("display_name")
        payload.pop("uid")
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status code check failed for missing uid and display name"
        self.log.info("[END] Testing with missing UID and display name")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.sanity
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35605')
    def test_35605(self):
        """
        Test create IAM User with mandatory/Non-mandatory parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with basic parameters")
        result, resp = self.csm_obj.verify_create_iam_user_rgw(user_type="valid",
                                                               verify_response=True)
        assert result, "Failed to create IAM user using basic parameters."
        self.log.info("Response : %s", resp)

        self.log.info("[END]Creating IAM user with basic parameters")
        self.created_iam_users.add(resp['tenant'] + "$" + resp['user_id'])

        self.log.info("[START] Creating IAM user with all parameters")
        result, resp = self.csm_obj.verify_create_iam_user_rgw(user_type="loaded",
                                                               verify_response=True)
        assert result, "Failed to create IAM user using all parameters."
        self.log.info("Response : %s", resp)
        self.log.info("[END]Creating IAM user with all parameters")
        self.created_iam_users.add(resp['tenant'] + "$" + resp['user_id'])
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35606')
    def test_35606(self):
        """
        Test create IAM User with Invalid Keys and Capability parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Testing with invalid access key")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"access_key": ""})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status check failed for invalid access key"
        self.log.info("[END] Testing with invalid access key")

        self.log.info("[START] Testing with invalid secret key")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"secret_key": ""})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status check failed forinvalid access key"
        self.log.info("[END] Testing with invalid secret key")

        self.log.info("[START] Testing with invalid key-type")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"key_type": "abc"})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status check failed for invalid key-type"
        self.log.info("[END] Testing with invalid key-type")

        self.log.info("[START] Testing with invalid capability parameter")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"user_caps": ""})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status check failed for invalid capability"
        self.log.info("[END] Testing with invalid capability parameter")

        self.log.info("[START] Testing with invalid token")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        self.log.info("payload :  %s", payload)
        headers = {'Authorization': 'abc'}
        resp = self.csm_obj.restapi.rest_call("post", endpoint=CSM_REST_CFG["s3_iam_user_endpoint"],
                                              json_dict=payload,
                                              headers=headers)
        assert resp.status_code == HTTPStatus.UNAUTHORIZED, "Status check failed for invalid token"
        self.log.info("[END] Testing with invalid token")

        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35607')
    def test_35607(self):
        """
        Test create IAM User with csm monitor user.( non admin)
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with basic parameters")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload,
                                                login_as="csm_user_monitor")
        assert resp.status_code == HTTPStatus.FORBIDDEN, \
            "Create user with Monitor user check failed."
        self.log.info("TODO Verify Response : %s", resp)
        self.log.info("[END]Creating IAM user with basic parameters")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35929')
    def test_35929(self):
        """
        Test create IAM User with random selection of optional parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with random selection of optional parameters")
        optional_payload = self.csm_obj.iam_user_payload_rgw("random")
        resp1 = self.csm_obj.create_iam_user_rgw(optional_payload)
        self.log.info("Verify Response : %s", resp1)
        assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED, \
                                 "IAM user creation failed")
        uid = resp1.json()["tenant"] + "$" + optional_payload['uid']
        self.created_iam_users.add(uid)
        self.log.info("Printing resp1 %s:", resp1)
        self.log.info("Printing optional payload %s:", optional_payload)
        resp = self.csm_obj.compare_iam_payload_response(resp1, optional_payload)
        self.log.info("compare payload response is: %s", resp)
        assert_utils.assert_true(resp[0], resp[1])
        self.log.info("Verified Response")
        self.log.info("[END]Creating IAM user with random selection of optional parameters")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35930')
    def test_35930(self):
        """
        Test create MAX IAM Users with random selection of optional parameters.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating %s IAM user with random selection of optional parameters",
                      const.MAX_IAM_USERS)
        for cnt in range(const.MAX_IAM_USERS):
            self.log.info("Creating IAM user number %s with random selection of optional "
                          "parameters", cnt)
            optional_payload = self.csm_obj.iam_user_payload_rgw("random")
            resp1 = self.csm_obj.create_iam_user_rgw(optional_payload)
            self.log.info("Verify Response : %s", resp1)
            assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED, \
                       "IAM user creation failed")
            uid = resp1.json()["tenant"] + "$" + optional_payload['uid']
            self.created_iam_users.add(uid)
            self.log.info("Printing resp %s:", resp1)
            self.log.info("Printing optional payload %s:", optional_payload)
            resp = self.csm_obj.compare_iam_payload_response(resp1, optional_payload)
            self.log.info("Printing response %s:", resp)
            assert_utils.assert_true(resp[0], resp[1])
        self.log.info("[END]Creating Max IAM user with random selection of optional parameters")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35931')
    def test_35931(self):
        """
        Test create IAM users with different tenant.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM users with different tenant")
        bucket_name = "iam-user-bucket-" + str(int(time.time()))
        for cnt in range(2):
            tenant = "tenant_" + str(cnt)
            self.log.info("Creating new iam user with tenant %s", tenant)
            optional_payload = self.csm_obj.iam_user_payload_rgw("loaded")
            optional_payload.update({"tenant": tenant})
            resp1 = self.csm_obj.create_iam_user_rgw(optional_payload)
            self.log.info("Verify Response : %s", resp1)
            assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED,
                            "IAM user creation failed")
            self.created_iam_users.add(resp1.json()['tenant'] + "$" + optional_payload['uid'])
            resp = self.csm_obj.compare_iam_payload_response(resp1, optional_payload)
            self.log.info("Printing response %s", resp)
            assert_utils.assert_true(resp[0], resp[1])
            self.log.info("Create bucket and perform IO")
            s3_obj = S3TestLib(access_key=resp1.json()["keys"][0]["access_key"],
                               secret_key=resp1.json()["keys"][0]["secret_key"])
            self.log.info("Step: Verify create bucket")
            status, resp = s3_obj.create_bucket(bucket_name)
            assert_utils.assert_true(status, resp)
            test_file = "test-object.txt"
            file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
            if os.path.exists(file_path_upload):
                os.remove(file_path_upload)
            if not os.path.isdir(TEST_DATA_FOLDER):
                self.log.debug("File path not exists, create a directory")
                system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
            system_utils.create_file(file_path_upload, self.file_size)
            self.log.info("Step: Verify put object.")
            resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                     file_path=file_path_upload)
            self.log.info("Removing uploaded object from a local path.")
            os.remove(file_path_upload)
            assert_utils.assert_true(resp[0], resp[1])
            self.log.info("Step: Verify get object.")
            resp = s3_obj.get_object(bucket_name, test_file)
            assert_utils.assert_true(resp[0], resp)
        self.log.info("[END]Creating IAM users with different tenant")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    # pylint: disable=broad-except
    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35932')
    def test_35932(self):
        """
        Test create IAM user with suspended true, and perform IO
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with suspended")
        uid = "iam_user_1_" + str(int(time.time()))
        bucket_name = "iam-user-bucket-" + str(int(time.time()))
        self.log.info("Creating new iam user  %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        payload.update({"suspended": True})
        resp1 = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp1)
        assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED,
                      "IAM user creation failed")
        self.created_iam_users.add(resp1.json()['tenant'] + "$" + uid)
        resp = self.csm_obj.compare_iam_payload_response(resp1, payload)
        assert_utils.assert_true(resp[0], resp[1])
        self.log.info("Verify create bucket")
        s3_obj = S3TestLib(access_key=resp1.json()["keys"][0]["access_key"],
                           secret_key=resp1.json()["keys"][0]["secret_key"])
        try:
            status, resp = s3_obj.create_bucket(bucket_name)
            self.log.info("Printing response %s", resp.json())
            assert_utils.assert_false(status, resp)
        except Exception as error:
            self.log.info("Expected exception received %s", error)
        self.log.info("[END]Creating IAM user with suspended")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35933')
    def test_35933(self):
        """
        Create user and check max bucket parameter
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with max bucket 1")
        uid = "iam_user_1_" + str(int(time.time()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        payload.update({"max_buckets": 1})
        resp1 = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp1)
        assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED,
                              "IAM user creation failed")
        self.created_iam_users.add(resp1.json()['tenant'] + "$" + uid)
        resp = self.csm_obj.compare_iam_payload_response(resp1, payload)
        assert_utils.assert_true(resp[0], resp[1])
        for bucket_cnt in range(2):
            bucket_name = "iam-user-bucket-" + str(bucket_cnt) + str(int(time.time()))
            # Create bucket with bucket_name and perform IO
            s3_obj = S3TestLib(access_key=resp1.json()["keys"][0]["access_key"],
                               secret_key=resp1.json()["keys"][0]["secret_key"])
            if bucket_cnt == 0:
                status, resp = s3_obj.create_bucket(bucket_name)
                assert_utils.assert_true(status, resp)
                test_file = "test-object.txt"
                file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
                if os.path.exists(file_path_upload):
                    os.remove(file_path_upload)
                if not os.path.isdir(TEST_DATA_FOLDER):
                    self.log.debug("File path not exists, create a directory")
                    system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
                system_utils.create_file(file_path_upload, self.file_size)
                resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                         file_path=file_path_upload)
                self.log.info("Removing uploaded object from a local path.")
                os.remove(file_path_upload)
                assert_utils.assert_true(resp[0], resp[1])
                self.log.info("Step: Verify get object.")
                resp = s3_obj.get_object(bucket_name, test_file)
                assert_utils.assert_true(resp[0], resp)
            else:
                try:
                    status, resp = s3_obj.create_bucket(bucket_name)
                    self.log.info("Printing response %s", resp.json())
                    assert_utils.assert_false(status, resp)
                except Exception as error:
                    self.log.info("Expected exception received %s", error)
        self.log.info("[END]Creating IAM user with max bucket 1")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35934')
    def test_35934(self):
        """
        Create user and check max bucket parameter
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with max buckets")
        payload = self.csm_obj.iam_user_payload_rgw("valid")
        resp1 = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp1)
        assert_utils.assert_true(resp1.status_code == HTTPStatus.CREATED,
                              "IAM user creation failed")
        self.created_iam_users.add(resp1.json()['tenant'] + "$" + payload["uid"])
        resp = self.csm_obj.compare_iam_payload_response(resp1, payload)
        self.log.info("Printing response %s", resp)
        assert_utils.assert_true(resp[0], resp[1])
        for bucket_cnt in range(const.MAX_BUCKETS+1):
            bucket_name = "iam-user-bucket-" + str(bucket_cnt) + str(int(time.time()))
            # Create bucket with bucket_name and perform IO
            s3_obj = S3TestLib(access_key=resp1.json()["keys"][0]["access_key"],
                               secret_key=resp1.json()["keys"][0]["secret_key"])
            status, resp = s3_obj.create_bucket(bucket_name)
            if bucket_cnt < const.MAX_BUCKETS:
                assert_utils.assert_true(status, resp)
                test_file = "test-object.txt"
                file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
                if os.path.exists(file_path_upload):
                    os.remove(file_path_upload)
                if not os.path.isdir(TEST_DATA_FOLDER):
                    self.log.debug("File path not exists, create a directory")
                    system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
                system_utils.create_file(file_path_upload, self.file_size)
                resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                         file_path=file_path_upload)
                self.log.info("Removing uploaded object from a local path.")
                os.remove(file_path_upload)
                assert_utils.assert_true(resp[0], resp[1])
                self.log.info("Step: Verify get object.")
                resp = s3_obj.get_object(bucket_name, test_file)
                assert_utils.assert_true(resp[0], resp)
            else:
                assert_utils.assert_false(status, resp)
        self.log.info("[END]Creating IAM user with max buckets")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-35935')
    def test_35935(self):
        """
        Create user with generate-keys=false
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user with generate-keys=false")
        self.log.info("Creating new iam user")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"generate_key": False})
        self.log.info(payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("printing resp %s:",resp.json())
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED.value, \
                     "IAM user creation failed")
        self.created_iam_users.add(resp.json()['tenant'] + "$" + payload["uid"])
        self.log.info("Printing keys %s", resp.json()["keys"])
        for key in resp.json()["keys"]:
            if "access_key" in key or "secret_key" in key:
                assert_utils.assert_true(False, "access and secret keys available in response")
        self.log.info("[END]Creating IAM user with generate-keys=false")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-36446')
    def test_36446(self):
        """
        Create user with read only capabilities.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info(
            "Step 1: Login using csm user and create a user with read capabilities")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        user_cap = "users=read"
        payload.update({"user_caps":user_cap})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.CREATED, \
            "User could not be created"
        self.created_iam_users.add(resp.json()['tenant'] + "$" + payload["uid"])
        self.log.info("Step 2: Create bucket and perform IO")
        bucket_name = "iam-user-bucket-" + str(int(time.time()))
        s3_obj = S3TestLib(access_key=resp.json()["keys"][0]["access_key"],
                           secret_key=resp.json()["keys"][0]["secret_key"])
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_false(status, resp)
        self.log.info("Create bucket failed for user")
        self.log.info("##### Test ended -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-36447')
    def test_36447(self):
        """
        Create user with invalid capabilities
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info(
            "Step 1: Login using csm user and create a user with invalid capabilities")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        payload.update({"user_caps": "read-write"})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.BAD_REQUEST, \
            "Status code check failed for user"
        self.log.info("##### Test ended -  %s #####", test_case_name)

    @pytest.mark.lc
    @pytest.mark.csmrest
    @pytest.mark.cluster_user_ops
    @pytest.mark.tags('TEST-36448')
    def test_36448(self):
        """
        User access/secret key validation.
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("Step 1: Login using csm user")
        payload = self.csm_obj.iam_user_payload_rgw(user_type="valid")
        #Uncomment this code when invalid access key combination is found
        #self.log.info("Step 1: Create a user with invalid access key")
        #invalid_key = self.csm_conf["test_36448"]["invalid_key"]
        #payload.update({"access_key": invalid_key})
        #self.log.info("payload :  %s", payload)
        #resp = self.csm_obj.create_iam_user_rgw(payload)
        #assert resp.status_code == HTTPStatus.BAD_REQUEST
        self.log.info("Step 2: create user with valid access key")
        valid_key = self.csm_conf["test_36448"]["valid_key"]
        payload.update({"access_key": valid_key})
        self.log.info("payload :  %s", payload)
        resp = self.csm_obj.create_iam_user_rgw(payload)
        assert resp.status_code == HTTPStatus.CREATED
        self.created_iam_users.add(resp.json()['tenant'] + "$" + payload["uid"])
        self.log.info("##### Test ended -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.sanity
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37016')
    def test_37016(self):
        """
        Delete user with userid
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        resp = resp.json()
        self.log.info("Create bucket and perform IO")
        s3_obj = S3TestLib(access_key=resp["keys"][0]["access_key"],
                           secret_key=resp["keys"][0]["secret_key"])
        self.log.info("Step: Verify create bucket")
        bucket_name = "user1" + str(int(time.time()))
        bucket_name = bucket_name.replace("_", "-")
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_true(status, resp)
        test_file = "test-object.txt"
        file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
        if os.path.exists(file_path_upload):
            os.remove(file_path_upload)
        if not os.path.isdir(TEST_DATA_FOLDER):
            self.log.debug("File path not exists, create a directory")
            system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
        system_utils.create_file(file_path_upload, self.file_size)
        self.log.info("Step: Verify put object.")
        resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                 file_path=file_path_upload)
        self.log.info("Removing uploaded object from a local path.")
        os.remove(file_path_upload)
        assert_utils.assert_true(resp[0], resp[1])
        get_resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        resp = self.csm_obj.compare_iam_payload_response(get_resp.json(), payload)
        self.log.debug(resp)
        assert_utils.assert_true(resp[0], "Value mismatch found")
        resp = s3_obj.delete_bucket(bucket_name=bucket_name, force=True)
        self.log.debug(resp)
        assert_utils.assert_true(resp[0], resp[1])
        resp = self.csm_obj.delete_iam_user(user=uid)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.OK, "IAM user deletion failed")
        self.created_iam_users.remove(uid)
        resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(resp.status_code == HTTPStatus.NOT_FOUND, "Deleted user exists")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37017')
    def test_37017(self):
        """
        Delete user with userid and purge-data
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        resp = resp.json()
        self.log.info("Create bucket and perform IO")
        s3_obj = S3TestLib(access_key=resp["keys"][0]["access_key"],
                           secret_key=resp["keys"][0]["secret_key"])
        self.log.info("Step: Verify create bucket")
        bucket_name = "user1" + str(int(time.time()))
        bucket_name = bucket_name.replace("_", "-")
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_true(status, resp)
        test_file = "test-object.txt"
        file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
        if os.path.exists(file_path_upload):
            os.remove(file_path_upload)
        if not os.path.isdir(TEST_DATA_FOLDER):
            self.log.debug("File path not exists, create a directory")
            system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
        system_utils.create_file(file_path_upload, self.file_size)
        self.log.info("Step: Verify put object.")
        resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                 file_path=file_path_upload)
        self.log.info("Removing uploaded object from a local path.")
        os.remove(file_path_upload)
        assert_utils.assert_true(resp[0], resp[1])
        get_resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        resp = self.csm_obj.compare_iam_payload_response(get_resp, payload)
        self.log.debug(resp)
        assert_utils.assert_true(resp[0], "Value mismatch found")
        resp = self.csm_obj.delete_iam_user(user=uid, purge_data=True)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.OK, "IAM user deletion failed")
        self.created_iam_users.remove(uid)
        resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(resp.status_code == HTTPStatus.NOT_FOUND, "Deleted user exists")
        # CORTX-29180 Need to add Check for buckets and objects created by users are deleted
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37019')
    def test_37019(self):
        """
        Remove user with not existing userid
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        resp = self.csm_obj.delete_iam_user(user=uid + "invalid", purge_data=True)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.NOT_FOUND, "Invalid user deleted")
        resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37014')
    def test_37014(self):
        """
        Create user and verify created user using get iam call
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        resp = self.csm_obj.compare_iam_payload_response(get_resp, payload)
        self.log.debug(resp)
        assert_utils.assert_true(resp[0], "Value mismatch found")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37015')
    def test_37015(self):
        """
        Delete IAM user with CSM user with no authority to delete it
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        mon_usr = CSM_REST_CFG["csm_user_monitor"]["username"]
        mon_pwd = CSM_REST_CFG["csm_user_monitor"]["password"]
        header = self.csm_obj.get_headers(mon_usr, mon_pwd)
        resp = self.csm_obj.delete_iam_user_rgw(uid, header)
        assert_utils.assert_true(resp.status_code == HTTPStatus.FORBIDDEN,
                                 "Monitor user deleted IAM user")
        get_resp = self.csm_obj.get_iam_user(uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        resp = self.csm_obj.compare_iam_payload_response(get_resp, payload)
        assert_utils.assert_true(resp[0], "Value mismatch found")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37020')
    def test_37020(self):
        """
        Get iam user using csm monitor user
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(user=uid, login_as="csm_user_monitor")
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        resp = self.csm_obj.compare_iam_payload_response(get_resp, payload)
        assert_utils.assert_true(resp[0], "Value mismatch found")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    # pylint: disable-msg=too-many-locals
    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37774')
    def test_37774(self):
        """
        Check users new access key generation
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        valid_key = self.csm_conf["test_36448"]["valid_key"] + "123"
        self.log.info("Adding key to user")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, access_key=valid_key)
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.OK, "Add key failed")
        resp = self.csm_obj.validate_added_deleted_keys(get_resp.json()["keys"], add_resp.json())
        self.log.info("Validate response: %s", resp)
        assert_utils.assert_true(resp[0], resp[1])
        access_key = resp[1][0]['access_key']
        secret_key = resp[1][0]['secret_key']
        assert_utils.assert_true(valid_key == access_key,
                                 "Added key is not matching to provided key")
        bucket_name = "iam_user_bucket_" + str(int(time.time()))
        self.log.info("Create bucket and perform IO")
        s3_obj = S3TestLib(access_key=access_key,
                           secret_key=secret_key)
        bucket_name = bucket_name.replace("_", "-")
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_true(status, resp)
        test_file = "test-object.txt"
        file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
        if os.path.exists(file_path_upload):
            os.remove(file_path_upload)
        if not os.path.isdir(TEST_DATA_FOLDER):
            self.log.debug("File path not exists, create a directory")
            system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
        system_utils.create_file(file_path_upload, self.file_size)
        self.log.info("Step: Verify put object.")
        resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                 file_path=file_path_upload)
        self.log.info("Removing uploaded object from a local path.")
        os.remove(file_path_upload)
        assert_utils.assert_true(resp[0], resp[1])
        self.log.info("Step: Verify get object.")
        resp = s3_obj.get_object(bucket_name, test_file)
        assert_utils.assert_true(resp[0], resp)
        self.log.info("##### Test completed -  %s #####", test_case_name)

    # pylint: disable-msg=too-many-locals
    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37775')
    def test_37775(self):
        """
        Check users new secret key generation
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        valid_key = self.csm_conf["test_36448"]["valid_key"]
        self.log.info("Adding key to user")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, secret_key=valid_key)
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.OK, "Add key failed")
        resp = self.csm_obj.validate_added_deleted_keys(get_resp.json()["keys"], add_resp.json())
        self.log.info("Validate response: %s", resp)
        assert_utils.assert_true(resp[0], resp[1])
        access_key = resp[1][0]['access_key']
        secret_key = resp[1][0]['secret_key']
        assert_utils.assert_true(valid_key == secret_key,
                                 "Added key is not matching to provided key")
        bucket_name = "iam_user_bucket_" + str(int(time.time()))
        self.log.info("Create bucket and perform IO")
        s3_obj = S3TestLib(access_key=access_key,
                           secret_key=secret_key)
        bucket_name = bucket_name.replace("_", "-")
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_true(status, resp)
        test_file = "test-object.txt"
        file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
        if os.path.exists(file_path_upload):
            os.remove(file_path_upload)
        if not os.path.isdir(TEST_DATA_FOLDER):
            self.log.debug("File path not exists, create a directory")
            system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
        system_utils.create_file(file_path_upload, self.file_size)
        self.log.info("Step: Verify put object.")
        resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                 file_path=file_path_upload)
        self.log.info("Removing uploaded object from a local path.")
        os.remove(file_path_upload)
        assert_utils.assert_true(resp[0], resp[1])
        self.log.info("Step: Verify get object.")
        resp = s3_obj.get_object(bucket_name, test_file)
        assert_utils.assert_true(resp[0], resp)
        self.log.info("##### Test completed -  %s #####", test_case_name)

    # pylint: disable-msg=too-many-locals
    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37776')
    def test_37776(self):
        """
        Create key request with existing access key of same user
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        access_key_init = get_resp.json()["keys"][0]['access_key']
        valid_key = self.csm_conf["test_36448"]["valid_key"]
        self.log.info("Adding key to user")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, access_key=access_key_init,
                                                    secret_key=valid_key)
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.OK, "Add key failed")
        assert_utils.assert_true(len(add_resp.json()) == 1, "More than 1 keys are received")
        access_key = add_resp.json()[0]['access_key']
        secret_key = add_resp.json()[0]['secret_key']
        assert_utils.assert_true(access_key == access_key_init, "Access key is not matching")
        assert_utils.assert_true(secret_key == valid_key, "Secret key is not matching")
        bucket_name = "iam_user_bucket_" + str(int(time.time()))
        self.log.info("Create bucket and perform IO")
        s3_obj = S3TestLib(access_key=access_key,
                           secret_key=secret_key)
        bucket_name = bucket_name.replace("_", "-")
        status, resp = s3_obj.create_bucket(bucket_name)
        assert_utils.assert_true(status, resp)
        test_file = "test-object.txt"
        file_path_upload = os.path.join(TEST_DATA_FOLDER, test_file)
        if os.path.exists(file_path_upload):
            os.remove(file_path_upload)
        if not os.path.isdir(TEST_DATA_FOLDER):
            self.log.debug("File path not exists, create a directory")
            system_utils.execute_cmd(cmd=common_cmd.CMD_MKDIR.format(TEST_DATA_FOLDER))
        system_utils.create_file(file_path_upload, self.file_size)
        self.log.info("Step: Verify put object.")
        resp = s3_obj.put_object(bucket_name=bucket_name, object_name=test_file,
                                 file_path=file_path_upload)
        self.log.info("Removing uploaded object from a local path.")
        os.remove(file_path_upload)
        assert_utils.assert_true(resp[0], resp[1])
        self.log.info("Step: Verify get object.")
        resp = s3_obj.get_object(bucket_name, test_file)
        assert_utils.assert_true(resp[0], resp)
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37777')
    def test_37777(self):
        """
        Create key request with existing access key of another user
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uids = []
        access_keys = []
        for user in range(2):
            uid = "iam_user_" + str(user) + str(int(time.time_ns()))
            self.log.info("Creating new iam user %s", uid)
            payload = self.csm_obj.iam_user_payload_rgw("loaded")
            payload.update({"uid": uid})
            payload.update({"display_name": uid})
            resp = self.csm_obj.create_iam_user_rgw(payload)
            self.log.info("Verify Response : %s", resp)
            assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED,
                                     "IAM user creation failed")
            uid = payload["tenant"] + "$" + uid
            uids.append(uid)
            self.created_iam_users.add(uid)
            get_resp = self.csm_obj.get_iam_user(user=uid)
            assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
            access_key = get_resp.json()["keys"][0]['access_key']
            access_keys.append(access_key)
        self.log.info("Adding key to user")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uids[0], access_key=access_keys[1])
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.CONFLICT, "Status Failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(add_resp.json()["message"] ==
                                     self.rest_resp_conf[12288]['EntityAlreadyExists'][1]
                                     , "Response failed")
        for user in range(2):
            get_resp = self.csm_obj.get_iam_user(user=uids[user])
            assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
            access_key = get_resp.json()["keys"][0]['access_key']
            assert_utils.assert_true(access_key == access_keys[user], "Access key is changed")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37778')
    def test_37778(self):
        """
        Create key request with empty access/secret keys
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        self.log.info("Adding empty key to user")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, access_key="")
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.BAD_REQUEST, "Response failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(add_resp.json()["message"] ==
                                     self.rest_resp_conf[4099]['empty key'][0]
                                     , "Response failed")
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, secret_key="")
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.BAD_REQUEST, "Response failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(add_resp.json()["message"] ==
                                     self.rest_resp_conf[4099]['empty key'][1]
                                     , "Response failed")
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        assert_utils.assert_true(len(get_resp.json()["keys"]) == 1, "Keys are modified")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37779')
    def test_37779(self):
        """
        Create key request with valid access key and no uid
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        valid_key = self.csm_conf["test_36448"]["valid_key"]
        add_resp = self.csm_obj.add_key_to_iam_user(uid=None, access_key=valid_key)
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.BAD_REQUEST, "Response failed")
        assert_utils.assert_true(add_resp.json()["error_code"] == "4099", "Response failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(add_resp.json()["message"] ==
                                     self.rest_resp_conf[4099]['empty key'][2]
                                     , "Response failed")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37780')
    def test_37780(self):
        """
        Remove access key of a user
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        access_key = resp.json()["keys"][0]['access_key']
        self.log.info("Removing key from user")
        rem_resp = self.csm_obj.remove_key_from_iam_user(uid=uid, access_key=access_key)
        assert_utils.assert_true(rem_resp.status_code == HTTPStatus.OK, "Remove key failed")
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        for key in get_resp.json()["keys"]:
            if "access_key" in key or "secret_key" in key:
                assert_utils.assert_true(False, "access or secret keys is not removed")
        uid2 = "iam_user_2_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid2)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid2})
        payload.update({"display_name": uid2})
        payload.update({"access_key": access_key})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid2 = payload["tenant"] + "$" + uid2
        self.created_iam_users.add(uid2)
        assert_utils.assert_true(access_key == resp.json()["keys"][0]['access_key'],
                                 "Access key is not matching")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37781')
    def test_37781(self):
        """
        Remove non-existing access key
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        access_key = resp.json()["keys"][0]['access_key']
        self.log.info("Removing key from user")
        rem_resp = self.csm_obj.remove_key_from_iam_user(uid=uid, access_key=access_key + "123")
        assert_utils.assert_true(rem_resp.status_code == HTTPStatus.FORBIDDEN,
                                 "Remove key status check failed")
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        assert_utils.assert_true(access_key == resp.json()["keys"][0]['access_key'],
                                 "Access key is not matching")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37782')
    def test_37782(self):
        """
        Try Removing access key with monitor role
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        access_key = resp.json()["keys"][0]['access_key']
        self.log.info("Removing key from user with csm monitor role")
        rem_resp = self.csm_obj.remove_key_from_iam_user(uid=uid, access_key=access_key,
                                                         login_as="csm_user_monitor")
        assert_utils.assert_true(rem_resp.status_code == HTTPStatus.FORBIDDEN,
                                 "Remove key status failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(rem_resp.json()["message"] ==
                                     self.rest_resp_conf[4101]['Access denied for account'][1]
                                     , "Response failed")
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        assert_utils.assert_true(access_key == get_resp.json()["keys"][0]['access_key'],
                                 "Access key is not matching")
        self.log.info("##### Test completed -  %s #####", test_case_name)

    @pytest.mark.csmrest
    @pytest.mark.lc
    @pytest.mark.cluster_user_ops
    @pytest.mark.parallel
    @pytest.mark.tags('TEST-37783')
    def test_37783(self):
        """
        Add access key with monitor role
        """
        test_case_name = cortxlogging.get_frame()
        self.log.info("##### Test started -  %s #####", test_case_name)
        self.log.info("[START] Creating IAM user")
        uid = "iam_user_1_" + str(int(time.time_ns()))
        self.log.info("Creating new iam user %s", uid)
        payload = self.csm_obj.iam_user_payload_rgw("loaded")
        payload.update({"uid": uid})
        payload.update({"display_name": uid})
        resp = self.csm_obj.create_iam_user_rgw(payload)
        self.log.info("Verify Response : %s", resp)
        assert_utils.assert_true(resp.status_code == HTTPStatus.CREATED, "IAM user creation failed")
        uid = payload["tenant"] + "$" + uid
        self.created_iam_users.add(uid)
        access_key = resp.json()["keys"][0]['access_key']
        add_resp = self.csm_obj.add_key_to_iam_user(uid=uid, access_key=access_key + "123",
                                                    login_as="csm_user_monitor")
        assert_utils.assert_true(add_resp.status_code == HTTPStatus.FORBIDDEN,
                                 "Add key status failed")
        if CSM_REST_CFG["msg_check"] == "enable":
            assert_utils.assert_true(add_resp.json()["message"] ==
                                     self.rest_resp_conf[4101]['Access denied for account'][1]
                                     , "Response failed")
        get_resp = self.csm_obj.get_iam_user(user=uid)
        assert_utils.assert_true(get_resp.status_code == HTTPStatus.OK, "Get IAM user failed")
        assert_utils.assert_true(access_key == get_resp.json()["keys"][0]['access_key'],
                                 "Access key is not matching")
        assert_utils.assert_true(len(get_resp.json()["keys"]) == 1,
                                 "Number of Access keys are not matching")
        self.log.info("##### Test completed -  %s #####", test_case_name)
