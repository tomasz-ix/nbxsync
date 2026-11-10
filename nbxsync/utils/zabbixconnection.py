from zabbix_utils import ZabbixAPI


class ZabbixConnection:
    def __init__(self, zabbixserver):
        self.zabbixserver = zabbixserver

        self._ZABBIX_AUTH = {'url': zabbixserver.url, 'validate_certs': zabbixserver.validate_certs}
        self.api = ZabbixAPI(**self._ZABBIX_AUTH, skip_version_check=self.zabbixserver.skip_version_check)

    def __enter__(self):
        # Attempt login
        try:
            self.api.login(token=self.zabbixserver.token)
        except Exception as e:
            raise ConnectionError(f'Failed to login to Zabbix: {e}')
        return self.api

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.api.logout()
        except Exception:
            pass  # Don't raise error on logout


class ZabbixConnections:
    """Zabbix API sessions that the operations of one job share, one per ZabbixServer.

    Each session opens (ZabbixConnection) on first use, and logs out when the block ends.
    Use as: with ZabbixConnections() as connections: connections.get(zabbixserver)
    """

    def __init__(self):
        self._sessions = {}  # ZabbixServer pk -> (ZabbixConnection, api)

    def __contains__(self, zabbixserver):
        return zabbixserver.pk in self._sessions

    def get(self, zabbixserver):
        if zabbixserver.pk not in self._sessions:
            connection = ZabbixConnection(zabbixserver)
            # Not cached if the login fails, so the next operation tries again
            api = connection.__enter__()
            self._sessions[zabbixserver.pk] = (connection, api)
        return self._sessions[zabbixserver.pk][1]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for connection, _api in self._sessions.values():
            connection.__exit__(None, None, None)
        self._sessions.clear()
