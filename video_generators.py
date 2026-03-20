import os
import random
import json
from datetime import datetime
from moviepy.editor import (
    VideoFileClip, TextClip, CompositeVideoClip,
    ColorClip, concatenate_videoclips
)
from moviepy.config import check_dependencies
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import tempfile
import logging

logger = logging.getLogger(__name__)

class VideoGenerator:
    def __init__(self, output_dir="generated_videos", max_size_mb=2):
        self.output_dir = output_dir
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024

        os.makedirs(output_dir, exist_ok=True)

        # Check MoviePy dependencies
        try:
            check_dependencies()
        except Exception as e:
            logger.warning(f"MoviePy dependencies check failed: {e}")

    def compress_video(self, input_path, output_path, target_bitrate=None):
        """Compress video to stay under size limit"""
        try:
            clip = VideoFileClip(input_path)
            duration = clip.duration

            if target_bitrate is None:
                # Calculate target bitrate for 90% of max size
                target_size = self.max_size_bytes * 0.9
                target_bitrate = int((target_size * 8) / duration / 1000)  # kbps

            # Clamp bitrate to reasonable range
            target_bitrate = max(100, min(target_bitrate, 1500))

            clip.write_videofile(
                output_path,
                bitrate=f"{target_bitrate}k",
                audio_bitrate="64k",
                temp_audiofile="temp_audio.m4a",
                remove_temp=True,
                codec='libx264',
                preset='medium'
            )
            clip.close()

            # Check final size
            if os.path.getsize(output_path) > self.max_size_bytes:
                # Try with lower bitrate
                return self.compress_video(input_path, output_path, target_bitrate // 2)

            return True

        except Exception as e:
            logger.error(f"Video compression failed: {e}")
            return False

    def generate_text_overlay_video(self, text_content, duration=15):
        """Generate a video with animated text overlays"""
        try:
            # Create background gradient
            width, height = 720, 480
            background = self._create_gradient_background(width, height, duration)

            # Split text into lines for better display
            lines = self._split_text_to_lines(text_content, max_chars=40)

            text_clips = []
            line_height = 60
            start_y = (height - len(lines) * line_height) // 2

            for i, line in enumerate(lines):
                text_clip = TextClip(
                    line,
                    fontsize=36,
                    color='white',
                    font='Arial-Bold'
                ).set_position(('center', start_y + i * line_height)).set_duration(duration)

                # Add fade in/out
                text_clip = text_clip.crossfadein(0.5).crossfadeout(0.5)
                text_clips.append(text_clip)

            # Compose video
            final_clip = CompositeVideoClip([background] + text_clips)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_path = os.path.join(self.output_dir, f"temp_text_{timestamp}.mp4")
            final_path = os.path.join(self.output_dir, f"text_overlay_{timestamp}.mp4")

            # Render temp video
            final_clip.write_videofile(temp_path, fps=24, codec='libx264')
            final_clip.close()

            # Compress
            if self.compress_video(temp_path, final_path):
                os.remove(temp_path)
                return final_path

        except Exception as e:
            logger.error(f"Text overlay video generation failed: {e}")

        return None

    def generate_animated_gradient_video(self, duration=20):
        """Generate an animated gradient background video"""
        try:
            width, height = 720, 480
            fps = 24
            frames = []

            for frame_num in range(int(duration * fps)):
                # Create animated gradient
                img = Image.new('RGB', (width, height))
                draw = ImageDraw.Draw(img)

                # Animated color values
                time_factor = frame_num / (duration * fps)
                r = int(128 + 127 * np.sin(time_factor * 2 * np.pi))
                g = int(128 + 127 * np.sin(time_factor * 2 * np.pi + 2))
                b = int(128 + 127 * np.sin(time_factor * 2 * np.pi + 4))

                # Create gradient
                for y in range(height):
                    gradient_factor = y / height
                    color_r = int(r * (1 - gradient_factor))
                    color_g = int(g * (1 - gradient_factor))
                    color_b = int(b * (1 - gradient_factor))
                    draw.line([(0, y), (width, y)], fill=(color_r, color_g, color_b))

                # Add some geometric shapes
                self._add_animated_shapes(draw, width, height, time_factor)

                frames.append(np.array(img))

            # Create video from frames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_path = os.path.join(self.output_dir, f"temp_gradient_{timestamp}.mp4")
            final_path = os.path.join(self.output_dir, f"gradient_{timestamp}.mp4")

            # Convert frames to video
            clip = ImageSequenceClip(frames, fps=fps)
            clip.write_videofile(temp_path, codec='libx264')
            clip.close()

            # Compress
            if self.compress_video(temp_path, final_path):
                os.remove(temp_path)
                return final_path

        except Exception as e:
            logger.error(f"Gradient video generation failed: {e}")

        return None

    def generate_code_visualization_video(self, code_snippets=None, duration=25):
        """Generate a code visualization video"""
        try:
            if code_snippets is None:
                code_snippets = self._get_sample_code_snippets()

            width, height = 720, 480

            # Create dark background
            background = ColorClip(size=(width, height), color=(30, 30, 30), duration=duration)

            clips = [background]

            # Add title
            title_clip = TextClip(
                "Code Visualization",
                fontsize=48,
                color='#00ff00',
                font='Courier-Bold'
            ).set_position(('center', 50)).set_duration(3).crossfadein(0.5)

            clips.append(title_clip)

            # Add code snippets with typewriter effect
            y_pos = 150
            snippet_duration = (duration - 5) / len(code_snippets)

            for i, snippet in enumerate(code_snippets):
                start_time = 3 + i * snippet_duration

                code_clip = TextClip(
                    snippet,
                    fontsize=24,
                    color='#ffffff',
                    font='Courier'
                ).set_position((50, y_pos)).set_start(start_time).set_duration(snippet_duration)

                clips.append(code_clip)
                y_pos += 80

                if y_pos > height - 100:
                    y_pos = 150

            # Compose final video
            final_clip = CompositeVideoClip(clips)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_path = os.path.join(self.output_dir, f"temp_code_{timestamp}.mp4")
            final_path = os.path.join(self.output_dir, f"code_viz_{timestamp}.mp4")

            final_clip.write_videofile(temp_path, fps=24, codec='libx264')
            final_clip.close()

            # Compress
            if self.compress_video(temp_path, final_path):
                os.remove(temp_path)
                return final_path

        except Exception as e:
            logger.error(f"Code visualization video generation failed: {e}")

        return None

    def _create_gradient_background(self, width, height, duration):
        """Create animated gradient background"""
        colors = [(255, 100, 100), (100, 255, 100), (100, 100, 255)]
        color_clip = ColorClip(size=(width, height), color=random.choice(colors), duration=duration)
        return color_clip

    def _split_text_to_lines(self, text, max_chars=40):
        """Split text into lines for better display"""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line + " " + word) <= max_chars:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines[:6]  # Limit to 6 lines

    def _add_animated_shapes(self, draw, width, height, time_factor):
        """Add animated geometric shapes to image"""
        # Animated circle
        center_x = width // 2 + int(100 * np.sin(time_factor * 4 * np.pi))
        center_y = height // 2 + int(50 * np.cos(time_factor * 4 * np.pi))
        radius = 30 + int(20 * np.sin(time_factor * 6 * np.pi))

        # Draw circle outline
        draw.ellipse(
            [center_x - radius, center_y - radius, center_x + radius, center_y + radius],
            outline=(255, 255, 255, 100)
        )

    def _get_sample_code_snippets(self):
        """Get sample code snippets for visualization"""
        snippets = [
            "def hello_world():",
            "    print('Hello, World!')",
            "",
            "class VideoBot:",
            "    def __init__(self):",
            "        self.active = True",
            "",
            "bot = VideoBot()",
            "bot.generate_content()",
            "",
            "# Automated content creation",
            "for day in range(7):",
            "    create_daily_video(day)"
        ]
        return snippets

    def generate_metadata(self, video_type="random"):
        """Generate title and description for videos"""
        titles = {
            "text": [
                "Daily Motivation: Success Mindset",
                "Tech Tips: Productivity Hacks",
                "Creative Inspiration for Today",
                "Daily Dose of Knowledge",
                "Mindful Moments: Stay Focused"
            ],
            "gradient": [
                "Relaxing Visual Experience",
                "Abstract Art in Motion",
                "Calming Gradients Collection",
                "Digital Art Therapy",
                "Visual Meditation Session"
            ],
            "code": [
                "Python Programming Tutorial",
                "Code Visualization Demo",
                "Learning to Code: Basics",
                "Programming Concepts Explained",
                "Daily Coding Practice"
            ]
        }

        descriptions = {
            "text": [
                "Daily motivational content to inspire your journey. Stay focused and achieve your goals!",
                "Quick tips and tricks to boost your productivity and efficiency.",
                "Get inspired with creative ideas and positive thoughts for today.",
                "Educational content to expand your knowledge and skills.",
                "Take a moment to center yourself and maintain focus throughout the day."
            ],
            "gradient": [
                "Enjoy this relaxing visual experience with smooth animated gradients.",
                "Abstract digital art designed to provide a calming viewing experience.",
                "Beautiful color transitions to help you relax and unwind.",
                "Digital art therapy session with soothing visual elements.",
                "A meditative visual journey through colors and shapes."
            ],
            "code": [
                "Learn programming concepts with this visual code demonstration.",
                "Educational coding content for beginners and intermediate learners.",
                "Step-by-step coding tutorial with clear explanations.",
                "Improve your programming skills with practical examples.",
                "Daily programming practice to enhance your coding abilities."
            ]
        }

        if video_type == "random":
            video_type = random.choice(["text", "gradient", "code"])

        title = random.choice(titles.get(video_type, titles["text"]))
        description = random.choice(descriptions.get(video_type, descriptions["text"]))

        # Add timestamp for uniqueness
        timestamp = datetime.now().strftime("%m/%d")
        title += f" - {timestamp}"

        return {
            "title": title,
            "description": description,
            "tags": ["automated", "daily", "content", video_type],
            "category": video_type
        }

    def generate_random_video(self, preferred_type=None):
        """Generate a random video of any type"""
        video_types = ["text", "gradient", "code"]

        if preferred_type and preferred_type in video_types:
            video_type = preferred_type
        else:
            video_type = random.choice(video_types)

        logger.info(f"Generating {video_type} video...")

        if video_type == "text":
            content = self._get_random_text_content()
            video_path = self.generate_text_overlay_video(content)
        elif video_type == "gradient":
            video_path = self.generate_animated_gradient_video()
        else:  # code
            video_path = self.generate_code_visualization_video()

        if video_path:
            metadata = self.generate_metadata(video_type)
            return {
                "video_path": video_path,
                "metadata": metadata,
                "type": video_type,
                "generated_at": datetime.now().isoformat()
            }

        return None

    def _get_random_text_content(self):
        """Get random text content for overlay videos"""
        content_options = [
            "Success comes to those who dare to begin. Take the first step today and transform your dreams into reality.",
            "Innovation distinguishes between a leader and a follower. Embrace change and create the future.",
            "The only way to do great work is to love what you do. Find your passion and pursue it relentlessly.",
            "Technology is advancing rapidly. Stay curious, keep learning, and adapt to the digital revolution.",
            "Creativity is intelligence having fun. Let your imagination guide you to new possibilities.",
            "Focus on progress, not perfection. Every small step forward brings you closer to your goals.",
            "Learning never stops. Embrace challenges as opportunities to grow and improve yourself.",
            "The future belongs to those who prepare for it today. Invest in yourself and your skills."
        ]

        return random.choice(content_options)
