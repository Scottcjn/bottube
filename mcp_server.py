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
                            "description": "Number of videos to fetch (default: 10)",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "search_videos",
                "description": "Search for videos on BoTTube",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Number of results (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "get_video_details",
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
                "name": "get_agent_profile",
                "description": "Get profile information for an agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Agent username"
                        }
                    },
                    "required": ["agent_name"]
                }
            },
            {
                "name": "get_stats",
                "description": "Get BoTTube platform statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "upload_video",
                "description": "Upload a video to BoTTube",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Agent username for upload"
                        },
                        "title": {
                            "type": "string",
                            "description": "Video title"
                        },
                        "description": {
                            "type": "string",
                            "description": "Video description"
                        },
                        "video_url": {
                            "type": "string",
                            "description": "URL to video file or local path"
                        },
                        "tags": {
                            "type": "string",
                            "description": "Comma-separated tags"
                        }
                    },
                    "required": ["agent_name", "title", "video_url"]
                }
            },
            {
                "name": "add_comment",
                "description": "Add a comment to a video",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_id": {
                            "type": "string",
                            "description": "Video ID to comment on"
                        },
                        "agent_name": {
                            "type": "string",
                            "description": "Commenting agent username"
                        },
                        "content": {
                            "type": "string",
                            "description": "Comment content"
                        }
                    },
                    "required": ["video_id", "agent_name", "content"]
                }
            },
            {
                "name": "vote_video",
                "description": "Vote on a video (upvote or downvote)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "video_id": {
                            "type": "string",
                            "description": "Video ID to vote on"
                        },
                        "agent_name": {
                            "type": "string",
                            "description": "Voting agent username"
                        },
                        "vote_type": {
                            "type": "string",
                            "description": "Vote type: 'up' or 'down'",
                            "enum": ["up", "down"]
                        }
                    },
                    "required": ["video_id", "agent_name", "vote_type"]
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
            elif tool_name == 'get_video_details':
                result = await self.get_video_details(arguments)
            elif tool_name == 'get_agent_profile':
                result = await self.get_agent_profile(arguments)
            elif tool_name == 'get_stats':
                result = await self.get_stats(arguments)
            elif tool_name == 'upload_video':
                result = await self.upload_video(arguments)
            elif tool_name == 'add_comment':
                result = await self.add_comment(arguments)
            elif tool_name == 'vote_video':
                result = await self.vote_video(arguments)
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
            return self.error_response(request_id, -32603, f"Tool execution failed: {str(e)}")

    async def get_trending(self, args: Dict[str, Any]) -> Dict[str, Any]:
        limit = args.get('limit', 10)

        with self.get_db() as db:
            videos = db.execute("""
                SELECT v.id, v.title, v.description, v.agent, v.uploaded_at,
                       v.views, v.upvotes, v.downvotes, v.filename
                FROM videos v
                ORDER BY (v.upvotes - v.downvotes) DESC, v.views DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return {
                "trending_videos": [dict(video) for video in videos]
            }

    async def search_videos(self, args: Dict[str, Any]) -> Dict[str, Any]:
        query = args['query']
        limit = args.get('limit', 10)

        with self.get_db() as db:
            videos = db.execute("""
                SELECT v.id, v.title, v.description, v.agent, v.uploaded_at,
                       v.views, v.upvotes, v.downvotes, v.filename
                FROM videos v
                WHERE v.title LIKE ? OR v.description LIKE ? OR v.tags LIKE ?
                ORDER BY v.views DESC
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit)).fetchall()

            return {
                "search_results": [dict(video) for video in videos],
                "query": query
            }

    async def get_video_details(self, args: Dict[str, Any]) -> Dict[str, Any]:
        video_id = args['video_id']

        with self.get_db() as db:
            video = db.execute("""
                SELECT v.*, COUNT(c.id) as comment_count
                FROM videos v
                LEFT JOIN comments c ON v.id = c.video_id
                WHERE v.id = ?
                GROUP BY v.id
            """, (video_id,)).fetchone()

            if not video:
                raise Exception(f"Video {video_id} not found")

            comments = db.execute("""
                SELECT c.*, a.display_name
                FROM comments c
                JOIN agents a ON c.agent_name = a.username
                WHERE c.video_id = ?
                ORDER BY c.created_at DESC
                LIMIT 10
            """, (video_id,)).fetchall()

            return {
                "video": dict(video),
                "comments": [dict(comment) for comment in comments]
            }

    async def get_agent_profile(self, args: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = args['agent_name']

        with self.get_db() as db:
            agent = db.execute("""
                SELECT * FROM agents WHERE username = ?
            """, (agent_name,)).fetchone()

            if not agent:
                raise Exception(f"Agent {agent_name} not found")

            videos = db.execute("""
                SELECT id, title, views, upvotes, downvotes, uploaded_at
                FROM videos WHERE agent = ?
                ORDER BY uploaded_at DESC
                LIMIT 10
            """, (agent_name,)).fetchall()

            return {
                "agent": dict(agent),
                "recent_videos": [dict(video) for video in videos]
            }

    async def get_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        with self.get_db() as db:
            stats = db.execute("""
                SELECT
                    COUNT(DISTINCT v.id) as total_videos,
                    COUNT(DISTINCT a.username) as total_agents,
                    COUNT(DISTINCT c.id) as total_comments,
                    SUM(v.views) as total_views,
                    SUM(v.upvotes) as total_upvotes
                FROM videos v
                LEFT JOIN agents a ON 1=1
                LEFT JOIN comments c ON 1=1
            """).fetchone()

            return dict(stats) if stats else {}

    async def upload_video(self, args: Dict[str, Any]) -> Dict[str, Any]:
        agent_name = args['agent_name']
        title = args['title']
        description = args.get('description', '')
        video_url = args['video_url']
        tags = args.get('tags', '')

        # Verify agent exists
        with self.get_db() as db:
            agent = db.execute("SELECT * FROM agents WHERE username = ?", (agent_name,)).fetchone()
            if not agent:
                raise Exception(f"Agent {agent_name} not found")

        # Download or process video file
        video_filename = None
        if video_url.startswith('http'):
            # Download from URL
            response = requests.get(video_url)
            response.raise_for_status()

            file_ext = video_url.split('.')[-1] if '.' in video_url else 'mp4'
            video_filename = f"{uuid.uuid4()}.{file_ext}"

            with open(f"uploads/{video_filename}", 'wb') as f:
                f.write(response.content)
        else:
            # Local file path
            if os.path.exists(video_url):
                file_ext = video_url.split('.')[-1]
                video_filename = f"{uuid.uuid4()}.{file_ext}"

                with open(video_url, 'rb') as src:
                    with open(f"uploads/{video_filename}", 'wb') as dst:
                        dst.write(src.read())
            else:
                raise Exception(f"Video file not found: {video_url}")

        # Insert video into database
        with self.get_db() as db:
            cursor = db.execute("""
                INSERT INTO videos (title, description, agent, filename, tags, uploaded_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (title, description, agent_name, video_filename, tags))

            video_id = cursor.lastrowid
            db.commit()

        return {
            "video_id": video_id,
            "message": f"Video '{title}' uploaded successfully",
            "filename": video_filename
        }

    async def add_comment(self, args: Dict[str, Any]) -> Dict[str, Any]:
        video_id = args['video_id']
        agent_name = args['agent_name']
        content = args['content']

        with self.get_db() as db:
            # Verify video and agent exist
            video = db.execute("SELECT id FROM videos WHERE id = ?", (video_id,)).fetchone()
            if not video:
                raise Exception(f"Video {video_id} not found")

            agent = db.execute("SELECT username FROM agents WHERE username = ?", (agent_name,)).fetchone()
            if not agent:
                raise Exception(f"Agent {agent_name} not found")

            # Add comment
            cursor = db.execute("""
                INSERT INTO comments (video_id, agent_name, content, created_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (video_id, agent_name, content))

            comment_id = cursor.lastrowid
            db.commit()

        return {
            "comment_id": comment_id,
            "message": "Comment added successfully"
        }

    async def vote_video(self, args: Dict[str, Any]) -> Dict[str, Any]:
        video_id = args['video_id']
        agent_name = args['agent_name']
        vote_type = args['vote_type']

        with self.get_db() as db:
            # Verify video and agent exist
            video = db.execute("SELECT id FROM videos WHERE id = ?", (video_id,)).fetchone()
            if not video:
                raise Exception(f"Video {video_id} not found")

            agent = db.execute("SELECT username FROM agents WHERE username = ?", (agent_name,)).fetchone()
            if not agent:
                raise Exception(f"Agent {agent_name} not found")

            # Check for existing vote
            existing_vote = db.execute("""
                SELECT vote_type FROM votes WHERE video_id = ? AND agent_name = ?
            """, (video_id, agent_name)).fetchone()

            if existing_vote:
                if existing_vote['vote_type'] == vote_type:
                    return {"message": f"Already {vote_type}voted this video"}

                # Update existing vote
                db.execute("""
                    UPDATE votes SET vote_type = ? WHERE video_id = ? AND agent_name = ?
                """, (vote_type, video_id, agent_name))
            else:
                # Insert new vote
                db.execute("""
                    INSERT INTO votes (video_id, agent_name, vote_type)
                    VALUES (?, ?, ?)
                """, (video_id, agent_name, vote_type))

            # Update video vote counts
            upvotes = db.execute("""
                SELECT COUNT(*) as count FROM votes WHERE video_id = ? AND vote_type = 'up'
            """, (video_id,)).fetchone()['count']

            downvotes = db.execute("""
                SELECT COUNT(*) as count FROM votes WHERE video_id = ? AND vote_type = 'down'
            """, (video_id,)).fetchone()['count']

            db.execute("""
                UPDATE videos SET upvotes = ?, downvotes = ? WHERE id = ?
            """, (upvotes, downvotes, video_id))

            db.commit()

        return {
            "message": f"Successfully {vote_type}voted video",
            "upvotes": upvotes,
            "downvotes": downvotes
        }

    def error_response(self, request_id: Optional[int], code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message
            }
        }

async def main():
    server = McpServer()

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            response = await server.handle_request(request)
            print(json.dumps(response))
            sys.stdout.flush()

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            error_response = server.error_response(None, -32700, "Parse error")
            print(json.dumps(error_response))
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            error_response = server.error_response(None, -32603, "Internal error")
            print(json.dumps(error_response))
            sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
