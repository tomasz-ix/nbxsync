from unittest.mock import MagicMock, patch

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from dcim.models import Device
from utilities.testing import create_test_device

from nbxsync.models import ZabbixConfigurationGroup, ZabbixServer, ZabbixServerAssignment
from nbxsync.systemjobs.sync_objects import SyncObjectsJob


class SyncObjectsSystemJobTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.server = ZabbixServer.objects.create(name='Zabbix Server 1', url='http://zabbix1.local', token='token1')
        cls.device1 = create_test_device(name='SyncObjects Dev 1')
        cls.device2 = create_test_device(name='SyncObjects Dev 2')
        cls.device_ct = ContentType.objects.get_for_model(Device)
        cls.cfg_ct = ContentType.objects.get_for_model(ZabbixConfigurationGroup)

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_enqueues_job_for_each_device(self, mock_get_queue):
        queue = MagicMock()
        mock_get_queue.return_value = queue

        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device2.pk)

        job = SyncObjectsJob(job=MagicMock())
        job.run()

        self.assertEqual(queue.create_job.call_count, 2)
        self.assertEqual(queue.enqueue_job.call_count, 2)

        enqueued_instances = [call.kwargs.get('args')[0] for call in queue.create_job.call_args_list]
        self.assertIn(self.device1, enqueued_instances)
        self.assertIn(self.device2, enqueued_instances)

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_passes_correct_args_to_create_job(self, mock_get_queue):
        queue = MagicMock()
        mock_get_queue.return_value = queue

        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)

        job = SyncObjectsJob(job=MagicMock())
        job.run()

        _, kwargs = queue.create_job.call_args
        self.assertEqual(kwargs.get('func'), 'nbxsync.worker.synchost')
        self.assertEqual(kwargs.get('timeout'), 9000)
        self.assertEqual(kwargs.get('args')[0], self.device1)

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_skips_configurationgroup_assignments(self, mock_get_queue):
        queue = MagicMock()
        mock_get_queue.return_value = queue

        cfg = ZabbixConfigurationGroup.objects.create(name='Test CFG', description='')
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.cfg_ct, assigned_object_id=cfg.pk)

        job = SyncObjectsJob(job=MagicMock())
        job.run()

        queue.create_job.assert_not_called()

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_stops_entirely_on_duplicate_assigned_object(self, mock_get_queue):
        queue = MagicMock()
        mock_get_queue.return_value = queue

        device3 = create_test_device(name='SyncObjects Dev 3')

        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)
        # Second assignment for device1 triggers the `return`
        server2 = ZabbixServer.objects.create(name='Zabbix Server 2', url='http://zabbix2.local', token='token2')
        ZabbixServerAssignment.objects.create(zabbixserver=server2, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=device3.pk)

        job = SyncObjectsJob(job=MagicMock())
        job.run()

        # Only device1 is enqueued; the loop exits on the duplicate before reaching device3
        self.assertEqual(queue.create_job.call_count, 2)
        enqueued_instances = [call.kwargs.get('args')[0] for call in queue.create_job.call_args_list]
        self.assertIn(self.device1, enqueued_instances)
        self.assertIn(device3, enqueued_instances)

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_does_nothing_when_no_assignments_exist(self, mock_get_queue):
        job = SyncObjectsJob(job=MagicMock())
        job.run()

        mock_get_queue.return_value.create_job.assert_not_called()

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_gets_queue_once(self, mock_get_queue):
        mock_get_queue.return_value = MagicMock()

        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device2.pk)

        SyncObjectsJob(job=MagicMock()).run()

        mock_get_queue.assert_called_once_with('low')

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_queries_do_not_grow_with_assignments(self, mock_get_queue):
        mock_get_queue.return_value = MagicMock()
        cfg = ZabbixConfigurationGroup.objects.create(name='Test CFG', description='')
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.cfg_ct, assigned_object_id=cfg.pk)
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)

        with CaptureQueriesContext(connection) as one:
            SyncObjectsJob(job=MagicMock()).run()

        for i in range(3):
            device = create_test_device(name=f'SyncObjects Query Dev {i}')
            ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=device.pk)

        with CaptureQueriesContext(connection) as four:
            SyncObjectsJob(job=MagicMock()).run()

        self.assertEqual(len(four), len(one))
        self.assertEqual(mock_get_queue.return_value.create_job.call_count, 1 + 4)

    @patch('nbxsync.systemjobs.sync_objects.get_queue')
    def test_run_enqueues_one_job_for_missing_objects(self, mock_get_queue):
        # An assignment whose object is gone gives one job with None, for all such assignments
        queue = MagicMock()
        mock_get_queue.return_value = queue

        server2 = ZabbixServer.objects.create(name='Zabbix Server 2', url='http://zabbix2.local', token='token2')
        gone = [
            ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device2.pk).pk,
            ZabbixServerAssignment.objects.create(zabbixserver=server2, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk).pk,
        ]
        ZabbixServerAssignment.objects.create(zabbixserver=self.server, assigned_object_type=self.device_ct, assigned_object_id=self.device1.pk)
        # save() validates the object, update() doesn't
        ZabbixServerAssignment.objects.filter(pk=gone[0]).update(assigned_object_id=999990)
        ZabbixServerAssignment.objects.filter(pk=gone[1]).update(assigned_object_id=999991)

        SyncObjectsJob(job=MagicMock()).run()

        enqueued_instances = [call.kwargs.get('args')[0] for call in queue.create_job.call_args_list]
        self.assertEqual(enqueued_instances.count(None), 1)
        self.assertIn(self.device1, enqueued_instances)
        self.assertEqual(len(enqueued_instances), 2)
