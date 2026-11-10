from nbxsync.models import ZabbixServer
from nbxsync.utils import ZabbixConnection


def run_zabbix_operation(sync_class, netbox_obj, operation, extra_args=None, connections=None):
    """
    Generic dispatcher to run a sync_class.{operation} on netbox_obj with a Zabbix connection.

    With connections (ZabbixConnections), the operation uses the session of the job for the
    Zabbix Server, and opens it on first use. Without, it opens a session for this operation only.
    """

    # Resolve ZabbixServer
    try:
        zabbixserver = sync_class.resolve_zabbixserver(netbox_obj)
    except AttributeError:
        netbox_obj.update_sync_info(success=False, message='Zabbix Server not assigned to object.')
        raise ValueError('Zabbix Server not assigned to object.')

    # A session of the job already has the server loaded
    if connections is None or zabbixserver not in connections:
        try:
            zabbixserver = ZabbixServer.objects.get(pk=zabbixserver.id)
        except ZabbixServer.DoesNotExist:
            netbox_obj.update_sync_info(success=False, message='Zabbix Server not found.')
            raise

    try:
        if connections is not None:
            return _run(connections.get(zabbixserver), sync_class, netbox_obj, operation, extra_args)

        with ZabbixConnection(zabbixserver) as api:
            return _run(api, sync_class, netbox_obj, operation, extra_args)

    except ConnectionError as e:
        netbox_obj.update_sync_info(success=False, message=f'Zabbix Login error: {e}')
        raise
    except Exception as e:
        netbox_obj.update_sync_info(success=False, message=f'Unexpected error: {e}')
        raise


def _run(api, sync_class, netbox_obj, operation, extra_args):
    sync_instance = sync_class(api, netbox_obj, **(extra_args or {}))

    method = getattr(sync_instance, operation, None)
    if not callable(method):
        raise NotImplementedError(f'{sync_class.__name__} does not implement `{operation}()`.')

    return method()
