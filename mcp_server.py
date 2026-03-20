import json
import sys
import asyncio
import sqlite3
import os
import tempfile
import uuid
from typing import Dict, Any, List, Optional
import requests
import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class McpServer:
    def __init__(self, db_path="bottube.db", base_url="http://localhost:5000"):
        self.db_path = db_path
        self.base_url = base_url

    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        try:
            method = request.get('method')
            params = request.get('params', {})
            request_id = request.get('id')

            if method == 'initialize':
                return await self.initialize(request_id)
            elif method == 'tools/list':
                return await self.list_tools(request_id)
            elif method == 'tools/call':
                return await self.call_tool(params, request_id)
            else:
                return self.error_response(request_id, -32601, f"Method {method} not found")

        except Exception as e:
            logger.error(f"Request handling error: {e}")
            return self.error_response(request.get('id'), -32603, str(e))

    async def initialize(self, request_id: int) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "bottube-mcp-server",
                    "version": "1.0.0"
                }
            }
        }

    async def list_tools(self, request_id: int) -> Dict[str, Any]:
        tools = [
            {
                "name": "get_trending",
                "description": "Get trending videos from BoTTube",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of videos to return (default: 10)",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "search_videos",
                "description": "Search for videos by title or creator",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results to return (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_video_info",
                "description": "Get detailed information about a specific video",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_id": {
                            "type": "string",
                            "description": "Video ID"
                        }
                    },
                    "required": ["video_id"]
                }
            },
            {
                "name": "upload_video",
                "description": "Upload a video to BoTTube",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Video title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Video description"
                        },
                        "video_path": {
                            "type": "string",
                            "description": "Path to video file"
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Agent/creator ID"
                        }
                    },
                    "required": ["title", "video_path", "agent_id"]
                }
            },
            {
                "name": "get_analytics",
                "description": "Get analytics data for a creator",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent/creator ID"
                        },
                        "period": {
                            "type": "string",
                            "description": "Time period (7d, 30d, 90d)",
                            "default": "30d"
                        }
                    },
                    "required": ["agent_id"]
                }
            },
            {
                "name": "create_playlist",
                "description": "Create a new playlist",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Playlist name"
                        },
                        "description": {
                            "type": "string",
                            "description": "Playlist description"
                        },
                        "agent_id": {
                            "type": "string",
                            "description": "Creator agent ID"
                        },
                        "is_public": {
                            "type": "boolean",
                            "description": "Whether playlist is public",
                            "default": True
                        }
                    },
                    "required": ["name", "agent_id"]
                }
            },
            {
                "name": "generate_content",
                "description": "Generate video content using AI",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Content generation prompt"
                        },
                        "type": {
                            "type": "string",
                            "description": "Content type (video, audio, image)",
                            "enum": ["video", "audio", "image"],
                            "default": "video"
                        },
                        "duration": {
                            "type": "integer",
                            "description": "Duration in seconds for video/audio",
                            "default": 30
                        }
                    },
                    "required": ["prompt"]
                }
            }
        ]

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools
            }
        }

    async def call_tool(self, params: Dict[str, Any], request_id: int) -> Dict[str, Any]:
        tool_name = params.get('name')
        arguments = params.get('arguments', {})

        try:
            if tool_name == 'get_trending':
                result = await self.get_trending(arguments)
            elif tool_name == 'search_videos':
                result = await self.search_videos(arguments)
            elif tool_name == 'get_video_info':
                result = await self.get_video_info(arguments)
            elif tool_name == 'upload_video':
                result = await self.upload_video(arguments)
            elif tool_name == 'get_analytics':
                result = await self.get_analytics(arguments)
            elif tool_name == 'create_playlist':
                result = await self.create_playlist(arguments)
            elif tool_name == 'generate_content':
                result = await self.generate_content(arguments)
            else:
                return self.error_response(request_id, -32601, f"Tool {tool_name} not found")

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2)
                        }
                    ]
                }
            }

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return self.error_response(request_id, -32603, str(e))

    async def get_trending(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = args.get('limit', 10)

        db = self.get_db()
        cursor = db.execute("""
            SELECT v.*, u.username as creator_name,
                   COUNT(vv.id) as view_count,
                   COUNT(l.id) as like_count
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            LEFT JOIN video_views vv ON v.id = vv.video_id
            LEFT JOIN likes l ON v.id = l.video_id AND l.type = 'like'
            WHERE v.visibility = 'public'
            GROUP BY v.id
            ORDER BY view_count DESC, v.created_at DESC
            LIMIT ?
        """, (limit,))

        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'creator': row['creator_name'],
                'views': row['view_count'],
                'likes': row['like_count'],
                'created_at': row['created_at'],
                'duration': row['duration']
            })

        db.close()
        return {'trending_videos': videos}

    async def search_videos(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = args.get('query')
        limit = args.get('limit', 10)

        db = self.get_db()
        search_term = f"%{query}%"
        cursor = db.execute("""
            SELECT v.*, u.username as creator_name,
                   COUNT(vv.id) as view_count
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            LEFT JOIN video_views vv ON v.id = vv.video_id
            WHERE (v.title LIKE ? OR v.description LIKE ? OR u.username LIKE ?)
                  AND v.visibility = 'public'
            GROUP BY v.id
            ORDER BY view_count DESC, v.created_at DESC
            LIMIT ?
        """, (search_term, search_term, search_term, limit))

        videos = []
        for row in cursor.fetchall():
            videos.append({
                'id': row['id'],
                'title': row['title'],
                'description': row['description'],
                'creator': row['creator_name'],
                'views': row['view_count'],
                'created_at': row['created_at']
            })

        db.close()
        return {'search_results': videos}

    async def get_video_info(self, args: Dict[str, Any]) -> Dict[str, Any]:
        video_id = args.get('video_id')

        db = self.get_db()
        cursor = db.execute("""
            SELECT v.*, u.username as creator_name,
                   COUNT(DISTINCT vv.id) as view_count,
                   COUNT(DISTINCT l.id) as like_count,
                   COUNT(DISTINCT c.id) as comment_count
            FROM videos v
            LEFT JOIN users u ON v.user_id = u.id
            LEFT JOIN video_views vv ON v.id = vv.video_id
            LEFT JOIN likes l ON v.id = l.video_id AND l.type = 'like'
            LEFT JOIN comments c ON v.id = c.video_id
            WHERE v.id = ?
            GROUP BY v.id
        """, (video_id,))

        row = cursor.fetchone()
        if not row:
            db.close()
            return {'error': 'Video not found'}

        video_info = {
            'id': row['id'],
            'title': row['title'],
            'description': row['description'],
            'creator': row['creator_name'],
            'views': row['view_count'],
            'likes': row['like_count'],
            'comments': row['comment_count'],
            'created_at': row['created_at'],
            'duration': row['duration'],
            'file_path': row['file_path']
        }

        db.close()
        return video_info

    async def upload_video(self, args: Dict[str, Any]) -> Dict[str, Any]:
        title = args.get('title')
        description = args.get('description', '')
        video_path = args.get('video_path')
        agent_id = args.get('agent_id')

        # Simulate video upload by making API request
        try:
            with open(video_path, 'rb') as video_file:
                files = {'video': video_file}
                data = {
                    'title': title,
                    'description': description
                }
                headers = {'X-Agent-ID': agent_id}

                response = requests.post(
                    f"{self.base_url}/upload",
                    files=files,
                    data=data,
                    headers=headers
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return {'error': f'Upload failed: {response.text}'}

        except Exception as e:
            return {'error': f'Upload error: {str(e)}'}

    async def get_analytics(self, args: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = args.get('agent_id')
        period = args.get('period', '30d')

        try:
            response = requests.get(
                f"{self.base_url}/analytics/api/views",
                params={'period': period},
                headers={'X-Agent-ID': agent_id}
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {'error': f'Analytics request failed: {response.text}'}

        except Exception as e:
            return {'error': f'Analytics error: {str(e)}'}

    async def create_playlist(self, args: Dict[str, Any]) -> Dict[str, Any]:
        name = args.get('name')
        description = args.get('description', '')
        agent_id = args.get('agent_id')
        is_public = args.get('is_public', True)

        db = self.get_db()
        try:
            cursor = db.execute("""
                INSERT INTO playlists (name, description, creator_id, is_public, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, description, agent_id, is_public, datetime.now().isoformat()))

            playlist_id = cursor.lastrowid
            db.commit()
            db.close()

            return {
                'playlist_id': playlist_id,
                'name': name,
                'description': description,
                'is_public': is_public,
                'message': 'Playlist created successfully'
            }

        except Exception as e:
            db.close()
            return {'error': f'Playlist creation failed: {str(e)}'}

    async def generate_content(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get('prompt')
        content_type = args.get('type', 'video')
        duration = args.get('duration', 30)

        # This is a placeholder for content generation
        # In a real implementation, you'd integrate with AI services

        temp_dir = tempfile.mkdtemp()
        output_file = None

        try:
            if content_type == 'video':
                output_file = os.path.join(temp_dir, f"generated_{uuid.uuid4().hex[:8]}.mp4")
                # Create a simple test video
                subprocess.run([
                    'ffmpeg', '-f', 'lavfi', '-i', 'testsrc2=duration={}:size=640x480:rate=30'.format(duration),
                    '-c:v', 'libx264', '-t', str(duration), output_file
                ], check=True, capture_output=True)

            elif content_type == 'audio':
                output_file = os.path.join(temp_dir, f"generated_{uuid.uuid4().hex[:8]}.mp3")
                # Create a simple test audio
                subprocess.run([
                    'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=440:duration={}'.format(duration),
                    output_file
                ], check=True, capture_output=True)

            elif content_type == 'image':
                output_file = os.path.join(temp_dir, f"generated_{uuid.uuid4().hex[:8]}.png")
                # Create a simple test image
                subprocess.run([
                    'ffmpeg', '-f', 'lavfi', '-i', 'testsrc2=size=640x480:duration=1',
                    '-frames:v', '1', output_file
                ], check=True, capture_output=True)

            return {
                'message': f'Generated {content_type} content',
                'file_path': output_file,
                'prompt': prompt,
                'type': content_type,
                'duration': duration if content_type != 'image' else None
            }

        except subprocess.CalledProcessError as e:
            return {'error': f'Content generation failed: {str(e)}'}
        except Exception as e:
            return {'error': f'Generation error: {str(e)}'}

    def error_response(self, request_id: int, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }


async def main():
    """Main MCP server loop."""
    server = McpServer()

    logger.info("BoTTube MCP Server starting...")

    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            request = json.loads(line.strip())
            response = await server.handle_request(request)

            print(json.dumps(response))
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            continue
        except Exception as e:
            logger.error(f"Server error: {e}")
            continue


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
