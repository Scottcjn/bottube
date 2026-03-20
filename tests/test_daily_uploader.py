import pytest
import tempfile
import os
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sqlite3
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from daily_uploader import DailyUploader, VideoGenerator, BoTTubeClient


class TestDailyUploader:

    @pytest.fixture
    def temp_db(self):
        """Create temporary database for testing"""
        fd, path = tempfile.mkstemp()
        os.close(fd)

        conn = sqlite3.connect(path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS uploaded_videos (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                bottube_id TEXT,
                status TEXT DEFAULT 'uploaded'
            )
        ''')
        conn.commit()
        conn.close()

        yield path
        os.unlink(path)

    @pytest.fixture
    def uploader(self, temp_db):
        """Create uploader instance with test database"""
        with patch.dict(os.environ, {
            'BOTTUBE_API_KEY': 'test_api_key',
            'DATABASE_PATH': temp_db
        }):
            return DailyUploader()

    def test_uploader_initialization(self, uploader):
        """Test that uploader initializes correctly"""
        assert uploader.api_key == 'test_api_key'
        assert uploader.video_generator is not None
        assert uploader.bottube_client is not None
        assert uploader.db_path is not None

    @patch('daily_uploader.VideoGenerator.generate_video')
    @patch('daily_uploader.BoTTubeClient.upload_video')
    def test_successful_daily_upload(self, mock_upload, mock_generate, uploader, temp_db):
        """Test successful video generation and upload"""
        # Setup mocks
        mock_generate.return_value = {
            'filename': 'test_video.mp4',
            'title': 'Daily Update - Tech News',
            'description': 'Latest tech news and updates for today'
        }
        mock_upload.return_value = {'id': 'video_123', 'status': 'success'}

        # Run upload
        result = uploader.upload_daily_video()

        # Verify results
        assert result['success'] is True
        assert result['video_id'] == 'video_123'
        mock_generate.assert_called_once()
        mock_upload.assert_called_once()

        # Check database record
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute('SELECT * FROM uploaded_videos WHERE bottube_id = ?', ('video_123',))
        record = cursor.fetchone()
        conn.close()

        assert record is not None
        assert record[1] == 'Daily Update - Tech News'

    def test_video_already_uploaded_today(self, uploader, temp_db):
        """Test skip when video already uploaded today"""
        # Insert today's record
        conn = sqlite3.connect(temp_db)
        conn.execute('''
            INSERT INTO uploaded_videos (title, filename, uploaded_at, bottube_id)
            VALUES (?, ?, ?, ?)
        ''', ('Test Video', 'test.mp4', datetime.now().isoformat(), 'existing_123'))
        conn.commit()
        conn.close()

        result = uploader.upload_daily_video()

        assert result['success'] is False
        assert 'already uploaded today' in result['message']

    @patch('daily_uploader.VideoGenerator.generate_video')
    def test_video_generation_failure(self, mock_generate, uploader):
        """Test handling of video generation failure"""
        mock_generate.side_effect = Exception("Generation failed")

        result = uploader.upload_daily_video()

        assert result['success'] is False
        assert 'Generation failed' in result['error']

    @patch('daily_uploader.VideoGenerator.generate_video')
    @patch('daily_uploader.BoTTubeClient.upload_video')
    def test_upload_failure_with_retry(self, mock_upload, mock_generate, uploader):
        """Test upload failure and retry mechanism"""
        mock_generate.return_value = {
            'filename': 'retry_video.mp4',
            'title': 'Retry Test Video',
            'description': 'Testing retry functionality'
        }

        # First call fails, second succeeds
        mock_upload.side_effect = [
            Exception("Network error"),
            {'id': 'retry_123', 'status': 'success'}
        ]

        result = uploader.upload_daily_video(max_retries=2)

        assert result['success'] is True
        assert result['video_id'] == 'retry_123'
        assert mock_upload.call_count == 2

    def test_get_upload_history(self, uploader, temp_db):
        """Test retrieval of upload history"""
        # Add test records
        conn = sqlite3.connect(temp_db)
        test_data = [
            ('Video 1', 'Daily content #1', 'vid1.mp4', datetime.now().isoformat(), 'bottube_1'),
            ('Video 2', 'Daily content #2', 'vid2.mp4', (datetime.now() - timedelta(days=1)).isoformat(), 'bottube_2'),
            ('Video 3', 'Daily content #3', 'vid3.mp4', (datetime.now() - timedelta(days=2)).isoformat(), 'bottube_3')
        ]

        for data in test_data:
            conn.execute('''
                INSERT INTO uploaded_videos (title, description, filename, uploaded_at, bottube_id)
                VALUES (?, ?, ?, ?, ?)
            ''', data)
        conn.commit()
        conn.close()

        history = uploader.get_upload_history(limit=5)

        assert len(history) == 3
        assert history[0]['title'] == 'Video 1'  # Most recent first
        assert history[0]['bottube_id'] == 'bottube_1'

    @patch('daily_uploader.subprocess.run')
    def test_scheduler_setup(self, mock_subprocess, uploader):
        """Test cron job scheduler setup"""
        uploader.setup_scheduler(schedule_time='14:30')

        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        assert 'crontab' in call_args
        assert '30 14 * * *' in ' '.join(call_args)

    def test_upload_status_tracking(self, uploader, temp_db):
        """Test status tracking for upload attempts"""
        # Test failed upload tracking
        uploader._record_upload_attempt('Failed Video', 'test_failed.mp4', 'Failed upload', status='failed')

        conn = sqlite3.connect(temp_db)
        cursor = conn.execute('SELECT status FROM uploaded_videos WHERE title = ?', ('Failed Video',))
        record = cursor.fetchone()
        conn.close()

        assert record[0] == 'failed'

        # Test upload statistics
        stats = uploader.get_upload_stats()
        assert 'total_attempts' in stats
        assert 'failed_uploads' in stats
        assert stats['failed_uploads'] == 1

    @patch('daily_uploader.VideoGenerator.generate_video')
    @patch('daily_uploader.BoTTubeClient.upload_video')
    @patch('os.path.exists')
    @patch('os.remove')
    def test_cleanup_after_upload(self, mock_remove, mock_exists, mock_upload, mock_generate, uploader):
        """Test cleanup of temporary files after upload"""
        mock_exists.return_value = True
        mock_generate.return_value = {
            'filename': 'temp_cleanup.mp4',
            'title': 'Cleanup Test',
            'description': 'Testing file cleanup'
        }
        mock_upload.return_value = {'id': 'cleanup_123', 'status': 'success'}

        result = uploader.upload_daily_video(cleanup_files=True)

        assert result['success'] is True
        mock_remove.assert_called_with('temp_cleanup.mp4')

    def test_unique_title_generation(self, uploader, temp_db):
        """Test that titles are unique across days"""
        # Add existing video
        conn = sqlite3.connect(temp_db)
        conn.execute('''
            INSERT INTO uploaded_videos (title, filename, uploaded_at, bottube_id)
            VALUES (?, ?, ?, ?)
        ''', ('Tech News Update', 'existing.mp4', (datetime.now() - timedelta(days=1)).isoformat(), 'existing_id'))
        conn.commit()
        conn.close()

        with patch('daily_uploader.VideoGenerator.generate_video') as mock_gen:
            # First attempt returns duplicate title
            mock_gen.side_effect = [
                {'filename': 'new.mp4', 'title': 'Tech News Update', 'description': 'desc'},
                {'filename': 'new2.mp4', 'title': 'Tech News Update - Today', 'description': 'desc'}
            ]

            with patch('daily_uploader.BoTTubeClient.upload_video') as mock_upload:
                mock_upload.return_value = {'id': 'unique_123', 'status': 'success'}

                result = uploader.upload_daily_video()

                assert result['success'] is True
                assert mock_gen.call_count == 2  # Called twice due to duplicate
