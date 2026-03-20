import os
import hashlib
import base64
import re
import logging
from urllib.parse import urlparse
from PIL import Image
import requests

logger = logging.getLogger(__name__)

class SEOOptimizer:
    def __init__(self):
        self.image_size_threshold = 500 * 1024  # 500KB
        self.max_image_dimension = 1920
        self.debug_patterns = [
            r'console\.(log|debug|info|warn|error)',
            r'debugger;?',
            r'alert\s*\(',
            r'//\s*TODO',
            r'//\s*FIXME',
            r'//\s*DEBUG'
        ]

    def validate_image_alt_text(self, html_content):
        """Check for images missing alt attributes or with poor alt text"""
        issues = []

        # Find all img tags
        img_pattern = r'<img[^>]*>'
        images = re.findall(img_pattern, html_content, re.IGNORECASE)

        for img_tag in images:
            # Check if alt attribute exists
            alt_match = re.search(r'alt\s*=\s*["\']([^"\']*)["\']', img_tag, re.IGNORECASE)
            src_match = re.search(r'src\s*=\s*["\']([^"\']*)["\']', img_tag, re.IGNORECASE)

            src = src_match.group(1) if src_match else 'unknown'

            if not alt_match:
                issues.append({
                    'type': 'missing_alt',
                    'src': src,
                    'message': f'Image missing alt attribute: {src}'
                })
            else:
                alt_text = alt_match.group(1)
                if not alt_text.strip():
                    issues.append({
                        'type': 'empty_alt',
                        'src': src,
                        'message': f'Image has empty alt attribute: {src}'
                    })
                elif len(alt_text) < 5 or alt_text.lower() in ['image', 'photo', 'picture']:
                    issues.append({
                        'type': 'poor_alt',
                        'src': src,
                        'alt': alt_text,
                        'message': f'Image has poor alt text: {src} - "{alt_text}"'
                    })

        logger.info(f"Found {len(issues)} image alt text issues")
        return issues

    def check_image_compression(self, image_paths):
        """Analyze images for size and compression optimization opportunities"""
        issues = []

        for img_path in image_paths:
            try:
                if not os.path.exists(img_path):
                    continue

                file_size = os.path.getsize(img_path)

                with Image.open(img_path) as img:
                    width, height = img.size
                    format_type = img.format

                    # Check file size
                    if file_size > self.image_size_threshold:
                        issues.append({
                            'type': 'oversized',
                            'path': img_path,
                            'size': file_size,
                            'message': f'Large image file: {img_path} ({file_size / 1024:.1f}KB)'
                        })

                    # Check dimensions
                    if width > self.max_image_dimension or height > self.max_image_dimension:
                        issues.append({
                            'type': 'large_dimensions',
                            'path': img_path,
                            'dimensions': f'{width}x{height}',
                            'message': f'Large image dimensions: {img_path} ({width}x{height})'
                        })

                    # Check format efficiency
                    if format_type in ['BMP', 'TIFF'] and file_size > 100 * 1024:
                        issues.append({
                            'type': 'inefficient_format',
                            'path': img_path,
                            'format': format_type,
                            'message': f'Inefficient image format: {img_path} ({format_type})'
                        })

            except Exception as e:
                logger.error(f"Error analyzing image {img_path}: {str(e)}")
                issues.append({
                    'type': 'analysis_error',
                    'path': img_path,
                    'error': str(e),
                    'message': f'Could not analyze image: {img_path}'
                })

        logger.info(f"Found {len(issues)} image compression issues")
        return issues

    def check_lazy_loading(self, html_content):
        """Check for images that should have lazy loading"""
        issues = []

        img_pattern = r'<img[^>]*>'
        images = re.findall(img_pattern, html_content, re.IGNORECASE)

        for img_tag in images:
            loading_match = re.search(r'loading\s*=\s*["\']([^"\']*)["\']', img_tag, re.IGNORECASE)
            src_match = re.search(r'src\s*=\s*["\']([^"\']*)["\']', img_tag, re.IGNORECASE)

            src = src_match.group(1) if src_match else 'unknown'

            # Check if image is likely above fold (skip lazy loading for hero images)
            is_hero = any(term in img_tag.lower() for term in ['hero', 'banner', 'logo'])

            if not loading_match and not is_hero:
                issues.append({
                    'type': 'missing_lazy_loading',
                    'src': src,
                    'message': f'Image should use lazy loading: {src}'
                })
            elif loading_match and loading_match.group(1) != 'lazy' and not is_hero:
                issues.append({
                    'type': 'incorrect_loading',
                    'src': src,
                    'loading': loading_match.group(1),
                    'message': f'Image has incorrect loading attribute: {src}'
                })

        logger.info(f"Found {len(issues)} lazy loading issues")
        return issues

    def detect_inline_scripts_styles(self, html_content):
        """Find inline scripts and styles that should be externalized"""
        issues = []

        # Find inline scripts
        script_pattern = r'<script(?![^>]*src\s*=)[^>]*>(.*?)</script>'
        inline_scripts = re.findall(script_pattern, html_content, re.DOTALL | re.IGNORECASE)

        for script_content in inline_scripts:
            script_content = script_content.strip()
            if script_content and len(script_content) > 100:
                issues.append({
                    'type': 'inline_script',
                    'size': len(script_content),
                    'preview': script_content[:100] + '...' if len(script_content) > 100 else script_content,
                    'message': f'Large inline script found ({len(script_content)} chars)'
                })

        # Find inline styles
        style_pattern = r'<style[^>]*>(.*?)</style>'
        inline_styles = re.findall(style_pattern, html_content, re.DOTALL | re.IGNORECASE)

        for style_content in inline_styles:
            style_content = style_content.strip()
            if style_content and len(style_content) > 100:
                issues.append({
                    'type': 'inline_style',
                    'size': len(style_content),
                    'preview': style_content[:100] + '...' if len(style_content) > 100 else style_content,
                    'message': f'Large inline style found ({len(style_content)} chars)'
                })

        logger.info(f"Found {len(issues)} inline script/style issues")
        return issues

    def generate_sri_hash(self, url_or_content, algorithm='sha384'):
        """Generate SRI hash for external resources"""
        try:
            if url_or_content.startswith(('http://', 'https://')):
                response = requests.get(url_or_content, timeout=10)
                response.raise_for_status()
                content = response.content
            else:
                content = url_or_content.encode('utf-8')

            hash_obj = hashlib.new(algorithm)
            hash_obj.update(content)
            hash_bytes = hash_obj.digest()
            hash_b64 = base64.b64encode(hash_bytes).decode('ascii')

            return f"{algorithm}-{hash_b64}"

        except Exception as e:
            logger.error(f"Error generating SRI hash: {str(e)}")
            return None

    def check_sri_attributes(self, html_content):
        """Check for external scripts missing SRI attributes"""
        issues = []

        # Find external script tags
        script_pattern = r'<script[^>]*src\s*=\s*["\']([^"\']*)["\'][^>]*>'
        external_scripts = re.findall(script_pattern, html_content, re.IGNORECASE)

        for script_match in re.finditer(script_pattern, html_content, re.IGNORECASE):
            full_tag = script_match.group(0)
            src = script_match.group(1)

            # Check if it's an external URL
            parsed = urlparse(src)
            if parsed.netloc and parsed.netloc not in ['localhost', '127.0.0.1']:
                # Check if integrity attribute exists
                if 'integrity=' not in full_tag:
                    issues.append({
                        'type': 'missing_sri',
                        'src': src,
                        'message': f'External script missing SRI: {src}'
                    })

        # Check external stylesheets
        link_pattern = r'<link[^>]*href\s*=\s*["\']([^"\']*)["\'][^>]*>'
        for link_match in re.finditer(link_pattern, html_content, re.IGNORECASE):
            full_tag = link_match.group(0)
            href = link_match.group(1)

            if 'rel="stylesheet"' in full_tag or 'rel=\'stylesheet\'' in full_tag:
                parsed = urlparse(href)
                if parsed.netloc and parsed.netloc not in ['localhost', '127.0.0.1']:
                    if 'integrity=' not in full_tag:
                        issues.append({
                            'type': 'missing_sri',
                            'src': href,
                            'message': f'External stylesheet missing SRI: {href}'
                        })

        logger.info(f"Found {len(issues)} SRI issues")
        return issues

    def detect_debug_artifacts(self, content, file_path=''):
        """Find debug artifacts that should be removed in production"""
        issues = []

        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            for pattern in self.debug_patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    issues.append({
                        'type': 'debug_artifact',
                        'file': file_path,
                        'line': line_num,
                        'content': line.strip(),
                        'pattern': pattern,
                        'message': f'Debug artifact found in {file_path}:{line_num}'
                    })

        logger.info(f"Found {len(issues)} debug artifacts in {file_path}")
        return issues

    def validate_metadata(self, html_content):
        """Validate OpenGraph, Twitter cards, and other metadata"""
        issues = []

        # Check for canonical URL
        canonical_pattern = r'<link[^>]*rel\s*=\s*["\']canonical["\'][^>]*>'
        if not re.search(canonical_pattern, html_content, re.IGNORECASE):
            issues.append({
                'type': 'missing_canonical',
                'message': 'Missing canonical URL'
            })

        # Check OpenGraph tags
        og_required = ['og:title', 'og:description', 'og:image', 'og:url']
        for og_tag in og_required:
            og_pattern = f'<meta[^>]*property\s*=\s*["\']?{re.escape(og_tag)}["\']?[^>]*>'
            if not re.search(og_pattern, html_content, re.IGNORECASE):
                issues.append({
                    'type': 'missing_opengraph',
                    'tag': og_tag,
                    'message': f'Missing OpenGraph tag: {og_tag}'
                })

        # Check Twitter card tags
        twitter_required = ['twitter:card', 'twitter:title', 'twitter:description']
        for twitter_tag in twitter_required:
            twitter_pattern = f'<meta[^>]*name\s*=\s*["\']?{re.escape(twitter_tag)}["\']?[^>]*>'
            if not re.search(twitter_pattern, html_content, re.IGNORECASE):
                issues.append({
                    'type': 'missing_twitter_card',
                    'tag': twitter_tag,
                    'message': f'Missing Twitter card tag: {twitter_tag}'
                })

        # Check for meta description
        desc_pattern = r'<meta[^>]*name\s*=\s*["\']description["\'][^>]*>'
        desc_match = re.search(desc_pattern, html_content, re.IGNORECASE)
        if not desc_match:
            issues.append({
                'type': 'missing_meta_description',
                'message': 'Missing meta description'
            })
        elif desc_match:
            content_match = re.search(r'content\s*=\s*["\']([^"\']*)["\']', desc_match.group(0))
            if content_match:
                desc_content = content_match.group(1)
                if len(desc_content) < 120 or len(desc_content) > 160:
                    issues.append({
                        'type': 'suboptimal_meta_description',
                        'length': len(desc_content),
                        'message': f'Meta description length suboptimal: {len(desc_content)} chars (ideal: 120-160)'
                    })

        # Check for robots meta
        robots_pattern = r'<meta[^>]*name\s*=\s*["\']robots["\'][^>]*>'
        if not re.search(robots_pattern, html_content, re.IGNORECASE):
            issues.append({
                'type': 'missing_robots_meta',
                'message': 'Missing robots meta tag'
            })

        logger.info(f"Found {len(issues)} metadata issues")
        return issues

    def run_comprehensive_audit(self, html_content, image_paths=None, additional_files=None):
        """Run all SEO optimization checks and return comprehensive report"""
        report = {
            'summary': {
                'total_issues': 0,
                'critical': 0,
                'warning': 0,
                'info': 0
            },
            'categories': {}
        }

        try:
            # Image alt text validation
            alt_issues = self.validate_image_alt_text(html_content)
            report['categories']['image_alt'] = alt_issues

            # Image compression checks
            if image_paths:
                compression_issues = self.check_image_compression(image_paths)
                report['categories']['image_compression'] = compression_issues

            # Lazy loading implementation
            lazy_issues = self.check_lazy_loading(html_content)
            report['categories']['lazy_loading'] = lazy_issues

            # Inline scripts/styles detection
            inline_issues = self.detect_inline_scripts_styles(html_content)
            report['categories']['inline_resources'] = inline_issues

            # SRI hash validation
            sri_issues = self.check_sri_attributes(html_content)
            report['categories']['sri'] = sri_issues

            # Metadata validation
            metadata_issues = self.validate_metadata(html_content)
            report['categories']['metadata'] = metadata_issues

            # Debug artifact detection
            debug_issues = self.detect_debug_artifacts(html_content, 'main.html')
            if additional_files:
                for file_path, content in additional_files.items():
                    debug_issues.extend(self.detect_debug_artifacts(content, file_path))
            report['categories']['debug_artifacts'] = debug_issues

            # Calculate summary
            all_issues = []
            for category, issues in report['categories'].items():
                all_issues.extend(issues)

            report['summary']['total_issues'] = len(all_issues)

            # Categorize by severity
            for issue in all_issues:
                if issue['type'] in ['missing_canonical', 'missing_meta_description', 'missing_opengraph']:
                    report['summary']['critical'] += 1
                elif issue['type'] in ['oversized', 'missing_sri', 'debug_artifact']:
                    report['summary']['warning'] += 1
                else:
                    report['summary']['info'] += 1

            logger.info(f"SEO audit completed: {report['summary']['total_issues']} total issues found")

        except Exception as e:
            logger.error(f"Error during comprehensive audit: {str(e)}")
            report['error'] = str(e)

        return report
