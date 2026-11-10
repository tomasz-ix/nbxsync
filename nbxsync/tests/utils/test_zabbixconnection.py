from unittest import TestCase
from unittest.mock import MagicMock, patch

from nbxsync.utils import ZabbixConnection, ZabbixConnections


class ZabbixConnectionTests(TestCase):
    def setUp(self):
        self.server = MagicMock()
        self.server.url = 'http://zabbix.example.com'
        self.server.token = 'secret-token'
        self.server.validate_certs = True

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_successful_connection(self, mock_api_class):
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api

        with ZabbixConnection(self.server) as api:
            mock_api.login.assert_called_once_with(token='secret-token')
            self.assertEqual(api, mock_api)

        mock_api.logout.assert_called_once()

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_login_failure_raises_connection_error(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.login.side_effect = Exception('Auth failed')
        mock_api_class.return_value = mock_api

        with self.assertRaises(ConnectionError) as cm:
            with ZabbixConnection(self.server):
                pass  # pragma: no cover

        self.assertIn('Failed to login to Zabbix', str(cm.exception))

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_logout_exception_is_suppressed(self, mock_api_class):
        mock_api = MagicMock()
        mock_api.logout.side_effect = Exception('Logout failed')
        mock_api_class.return_value = mock_api

        # Should not raise anything
        with ZabbixConnection(self.server) as api:
            pass

        mock_api.logout.assert_called_once()


class ZabbixConnectionsTests(TestCase):
    def setUp(self):
        self.server = MagicMock(pk=1, url='http://zabbix.example.com', token='secret-token', validate_certs=True)
        self.other_server = MagicMock(pk=2, url='http://zabbix2.example.com', token='other-token', validate_certs=True)

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_one_session_per_server(self, mock_api_class):
        apis = [MagicMock(), MagicMock()]
        mock_api_class.side_effect = apis

        with ZabbixConnections() as connections:
            self.assertNotIn(self.server, connections)
            first = connections.get(self.server)
            self.assertIn(self.server, connections)
            self.assertIs(connections.get(self.server), first)
            other = connections.get(self.other_server)

        self.assertIs(first, apis[0])
        self.assertIs(other, apis[1])
        self.assertEqual(mock_api_class.call_count, 2)
        apis[0].login.assert_called_once_with(token='secret-token')
        apis[1].login.assert_called_once_with(token='other-token')
        apis[0].logout.assert_called_once()
        apis[1].logout.assert_called_once()
        self.assertNotIn(self.server, connections)

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_failed_login_is_not_cached(self, mock_api_class):
        failing, working = MagicMock(), MagicMock()
        failing.login.side_effect = Exception('Auth failed')
        mock_api_class.side_effect = [failing, working]

        with ZabbixConnections() as connections:
            with self.assertRaises(ConnectionError):
                connections.get(self.server)
            self.assertNotIn(self.server, connections)
            self.assertIs(connections.get(self.server), working)

        failing.logout.assert_not_called()
        working.logout.assert_called_once()

    @patch('nbxsync.utils.zabbixconnection.ZabbixAPI')
    def test_logs_out_when_block_raises(self, mock_api_class):
        mock_api = MagicMock()
        mock_api_class.return_value = mock_api

        with self.assertRaises(ValueError), ZabbixConnections() as connections:
            connections.get(self.server)
            raise ValueError('sync failed')

        mock_api.logout.assert_called_once()
