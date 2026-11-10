from django.contrib.contenttypes.models import ContentType
from django_rq import get_queue

from netbox.jobs import JobRunner, system_job

from nbxsync.models import ZabbixServerAssignment, ZabbixConfigurationGroup
from nbxsync.settings import get_plugin_settings


def GetSyncInterval():
    pluginsettings = get_plugin_settings()
    return pluginsettings.backgroundsync.objects.interval


def _object_key(instance):
    # The same identity as Model.__eq__: concrete model and primary key
    if instance is None:
        return None
    return (instance._meta.concrete_model, instance.pk)


@system_job(interval=GetSyncInterval())
class SyncObjectsJob(JobRunner):
    class Meta:
        name = 'Zabbix Sync Hosts job'

    def run(self, *args, **kwargs):
        # dont try to sync ZabbixConfigurationGroups
        configgroup_type = ContentType.objects.get_for_model(ZabbixConfigurationGroup)
        assignments = ZabbixServerAssignment.objects.exclude(assigned_object_type=configgroup_type).prefetch_related('assigned_object')

        synced_objects = set()
        queue = get_queue('low')
        for obj in assignments:
            instance = obj.assigned_object

            key = _object_key(instance)
            if key in synced_objects:
                continue
            synced_objects.add(key)

            queue.enqueue_job(
                queue.create_job(
                    func='nbxsync.worker.synchost',
                    args=[instance],
                    timeout=9000,
                )
            )
