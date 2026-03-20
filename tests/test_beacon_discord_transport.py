# SPDX-License-Identifier: MIT

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import time
from datetime import datetime, timedelta

from bottube_server import app


class TestBeaconDiscordTransport(unittest.TestCase):
    """Comprehensive test suite for Discord transport hardening"""

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Mock Discord webhook URL
        self.webhook_url = "https://discord.com/api/webhooks/123456789/test_webhook_token"

        # Sample beacon payload
        self.beacon_payload = {
            "type": "test_event",
            "timestamp": "2024-01-15T10:30:00Z",
            "source": "test_node",
            "data": {"status": "active", "value": 42}
        }

    def test_rate_limit_handling_429(self):
        """Test Discord 429 rate limit response handling"""
        with patch('requests.post') as mock_post:
            # First call returns 429 with retry-after header
            mock_response_429 = Mock()
            mock_response_429.status_code = 429
            mock_response_429.headers = {'retry-after': '2', 'x-ratelimit-global': 'false'}
            mock_response_429.json.return_value = {
                'retry_after': 2.5,
                'global': False,
                'message': 'You are being rate limited.'
            }

            # Second call succeeds
            mock_response_success = Mock()
            mock_response_success.status_code = 204
            mock_response_success.headers = {}

            mock_post.side_effect = [mock_response_429, mock_response_success]

            # Test rate limit retry logic
            response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': self.beacon_payload
                })

            # Should succeed after retry
            self.assertEqual(response.status_code, 200)
            self.assertEqual(mock_post.call_count, 2)

    def test_global_rate_limit_handling(self):
        """Test Discord global rate limit handling"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 429
            mock_response.headers = {'retry-after': '5', 'x-ratelimit-global': 'true'}
            mock_response.json.return_value = {
                'retry_after': 5.0,
                'global': True,
                'message': 'You are being rate limited.'
            }

            mock_post.return_value = mock_response

            response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': self.beacon_payload
                })

            # Should fail after max retries for global rate limit
            self.assertEqual(response.status_code, 429)
            data = response.get_json()
            self.assertIn('rate_limited', data.get('error', ''))

    def test_webhook_4xx_error_parsing(self):
        """Test Discord webhook 4xx error response parsing"""
        test_cases = [
            {
                'status_code': 400,
                'response': {'message': 'Invalid webhook token', 'code': 50027},
                'expected_error': 'webhook_invalid'
            },
            {
                'status_code': 401,
                'response': {'message': 'Unauthorized', 'code': 0},
                'expected_error': 'auth_failed'
            },
            {
                'status_code': 404,
                'response': {'message': 'Unknown Webhook', 'code': 10015},
                'expected_error': 'webhook_not_found'
            }
        ]

        for case in test_cases:
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = case['status_code']
                mock_response.json.return_value = case['response']
                mock_post.return_value = mock_response

                response = self.client.post('/api/beacon/discord/send',
                    json={
                        'webhook_url': self.webhook_url,
                        'payload': self.beacon_payload
                    })

                self.assertEqual(response.status_code, case['status_code'])
                data = response.get_json()
                self.assertIn(case['expected_error'], data.get('error', ''))

    def test_webhook_5xx_retry_logic(self):
        """Test Discord webhook 5xx error retry logic"""
        with patch('requests.post') as mock_post:
            # First two calls return 502 (bad gateway)
            mock_response_502 = Mock()
            mock_response_502.status_code = 502
            mock_response_502.json.return_value = {'message': 'Bad Gateway'}

            # Third call succeeds
            mock_response_success = Mock()
            mock_response_success.status_code = 204

            mock_post.side_effect = [mock_response_502, mock_response_502, mock_response_success]

            response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': self.beacon_payload,
                    'retry_config': {'max_retries': 3, 'backoff_factor': 0.1}
                })

            self.assertEqual(response.status_code, 200)
            self.assertEqual(mock_post.call_count, 3)

    def test_dry_run_payload_validation(self):
        """Test dry-run mode payload validation without sending"""
        test_payloads = [
            # Valid payload
            {
                'payload': self.beacon_payload,
                'should_pass': True
            },
            # Missing required fields
            {
                'payload': {'type': 'incomplete'},
                'should_pass': False,
                'error': 'missing_timestamp'
            },
            # Invalid timestamp format
            {
                'payload': {
                    'type': 'test',
                    'timestamp': 'invalid-date',
                    'source': 'test'
                },
                'should_pass': False,
                'error': 'invalid_timestamp'
            },
            # Payload too large
            {
                'payload': {
                    'type': 'large_test',
                    'timestamp': '2024-01-15T10:30:00Z',
                    'source': 'test',
                    'data': {'large_field': 'x' * 2000}
                },
                'should_pass': False,
                'error': 'payload_too_large'
            }
        ]

        for case in test_payloads:
            response = self.client.post('/api/beacon/discord/validate',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': case['payload'],
                    'dry_run': True
                })

            if case['should_pass']:
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertTrue(data.get('valid', False))
                self.assertIn('discord_payload', data)
            else:
                self.assertIn(response.status_code, [400, 413])
                data = response.get_json()
                self.assertFalse(data.get('valid', True))
                if 'error' in case:
                    self.assertIn(case['error'], data.get('error', ''))

    def test_ping_connectivity(self):
        """Test Discord ping connectivity check"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 204
            mock_response.headers = {'x-ratelimit-remaining': '4', 'x-ratelimit-reset': '1642248600'}
            mock_post.return_value = mock_response

            response = self.client.post('/api/beacon/discord/ping',
                json={'webhook_url': self.webhook_url})

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertTrue(data.get('connected', False))
            self.assertIn('rate_limit_info', data)

    def test_listener_mode_polling(self):
        """Test Discord listener mode polling for events"""
        with patch('requests.get') as mock_get:
            # Mock Discord channel messages endpoint
            mock_messages = [
                {
                    'id': '123456789',
                    'content': json.dumps(self.beacon_payload),
                    'timestamp': '2024-01-15T10:30:00Z',
                    'author': {'username': 'BeaconBot'}
                }
            ]

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_messages
            mock_get.return_value = mock_response

            response = self.client.post('/api/beacon/discord/listen',
                json={
                    'channel_id': '987654321',
                    'bot_token': 'Bot test_token',
                    'since': '2024-01-15T10:00:00Z',
                    'filter_author': 'BeaconBot'
                })

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            self.assertIn('events', data)
            self.assertEqual(len(data['events']), 1)
            self.assertEqual(data['events'][0]['type'], 'test_event')

    def test_listener_message_filtering(self):
        """Test listener mode message filtering and parsing"""
        with patch('requests.get') as mock_get:
            mixed_messages = [
                {
                    'id': '1',
                    'content': json.dumps(self.beacon_payload),
                    'timestamp': '2024-01-15T10:30:00Z',
                    'author': {'username': 'BeaconBot'}
                },
                {
                    'id': '2',
                    'content': 'Regular chat message',
                    'timestamp': '2024-01-15T10:31:00Z',
                    'author': {'username': 'User123'}
                },
                {
                    'id': '3',
                    'content': json.dumps({'type': 'status_update', 'timestamp': '2024-01-15T10:32:00Z'}),
                    'timestamp': '2024-01-15T10:32:00Z',
                    'author': {'username': 'BeaconBot'}
                }
            ]

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mixed_messages
            mock_get.return_value = mock_response

            response = self.client.post('/api/beacon/discord/listen',
                json={
                    'channel_id': '987654321',
                    'bot_token': 'Bot test_token',
                    'filter_author': 'BeaconBot',
                    'parse_json_only': True
                })

            self.assertEqual(response.status_code, 200)
            data = response.get_json()
            # Should only return valid JSON messages from BeaconBot
            self.assertEqual(len(data['events']), 2)

    def test_integration_send_and_listen(self):
        """Test integration scenario: send beacon then listen for confirmation"""
        with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
            # Mock successful send
            mock_send_response = Mock()
            mock_send_response.status_code = 204
            mock_post.return_value = mock_send_response

            # Send beacon
            send_response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': self.beacon_payload
                })

            self.assertEqual(send_response.status_code, 200)

            # Mock listener finding the sent message
            echo_payload = self.beacon_payload.copy()
            echo_payload['echo'] = True

            mock_listen_response = Mock()
            mock_listen_response.status_code = 200
            mock_listen_response.json.return_value = [
                {
                    'id': '999',
                    'content': json.dumps(echo_payload),
                    'timestamp': '2024-01-15T10:31:00Z',
                    'author': {'username': 'BeaconBot'}
                }
            ]
            mock_get.return_value = mock_listen_response

            # Listen for confirmation
            listen_response = self.client.post('/api/beacon/discord/listen',
                json={
                    'channel_id': '987654321',
                    'bot_token': 'Bot test_token',
                    'since': '2024-01-15T10:30:00Z'
                })

            self.assertEqual(listen_response.status_code, 200)
            data = listen_response.get_json()
            self.assertTrue(data['events'][0]['echo'])

    def test_exponential_backoff_timing(self):
        """Test exponential backoff timing for retries"""
        with patch('requests.post') as mock_post, patch('time.sleep') as mock_sleep:
            # Mock consecutive failures
            mock_response = Mock()
            mock_response.status_code = 500
            mock_post.return_value = mock_response

            response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': self.webhook_url,
                    'payload': self.beacon_payload,
                    'retry_config': {
                        'max_retries': 3,
                        'backoff_factor': 1.0,
                        'max_backoff': 10.0
                    }
                })

            # Should have called sleep with increasing delays
            expected_delays = [1.0, 2.0, 4.0]  # exponential backoff
            actual_delays = [call[0][0] for call in mock_sleep.call_args_list]

            self.assertEqual(len(actual_delays), 3)
            for expected, actual in zip(expected_delays, actual_delays):
                self.assertAlmostEqual(actual, expected, delta=0.1)

    def test_malformed_webhook_url_handling(self):
        """Test handling of malformed webhook URLs"""
        malformed_urls = [
            'not-a-url',
            'http://example.com/not-discord',
            'https://discord.com/api/webhooks/invalid',
            'https://discord.com/api/webhooks/123/missing-token/'
        ]

        for url in malformed_urls:
            response = self.client.post('/api/beacon/discord/send',
                json={
                    'webhook_url': url,
                    'payload': self.beacon_payload
                })

            self.assertEqual(response.status_code, 400)
            data = response.get_json()
            self.assertIn('invalid_webhook_url', data.get('error', ''))

    def test_concurrent_request_handling(self):
        """Test handling of concurrent Discord requests"""
        import threading
        import queue

        results = queue.Queue()

        def make_request():
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 204
                mock_post.return_value = mock_response

                response = self.client.post('/api/beacon/discord/send',
                    json={
                        'webhook_url': self.webhook_url,
                        'payload': self.beacon_payload
                    })
                results.put(response.status_code)

        # Start multiple concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all to complete
        for thread in threads:
            thread.join()

        # All should succeed
        while not results.empty():
            status = results.get()
            self.assertEqual(status, 200)


if __name__ == '__main__':
    unittest.main()
