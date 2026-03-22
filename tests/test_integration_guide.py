"""
Tests for BoTTube Integration Guide

Verifies code examples are valid and documentation is complete.
"""

import os
import re
import pytest

DOCS_PATH = "docs/INTEGRATION_POST.md"


class TestIntegrationGuide:
    """Test suite for integration guide quality"""
    
    def test_guide_exists(self):
        """Test that integration guide exists"""
        assert os.path.exists(DOCS_PATH), f"Guide {DOCS_PATH} not found"
    
    def test_guide_has_content(self):
        """Test that guide has substantial content"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert len(content) > 1000, "Guide too short"
    
    def test_has_python_example(self):
        """Test Python code example is present"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "from bottube import" in content or "import bottube" in content
    
    def test_has_nodejs_example(self):
        """Test Node.js code example is present"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "require('@bottube" in content or "from '@bottube" in content
    
    def test_has_api_reference(self):
        """Test API reference section exists"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "API" in content or "Endpoint" in content
    
    def test_has_authentication(self):
        """Test authentication section exists"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "Authentication" in content or "API key" in content
    
    def test_has_troubleshooting(self):
        """Test troubleshooting section exists"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "Troubleshooting" in content or "Error" in content
    
    def test_has_backlink(self):
        """Test backlink to BoTTube is present"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        assert "bottube.io" in content or "github.com/Scottcjn/bottube" in content
    
    def test_code_blocks_valid(self):
        """Test code blocks are properly formatted"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        # Count code blocks
        code_blocks = re.findall(r'```[\s\S]*?```', content)
        assert len(code_blocks) >= 3, "Not enough code examples"
    
    def test_sections_complete(self):
        """Test all required sections are present"""
        with open(DOCS_PATH, 'r') as f:
            content = f.read()
        
        required_sections = [
            "Installation",
            "Quick Start",
            "API",
            "Authentication"
        ]
        
        for section in required_sections:
            assert section in content, f"Missing section: {section}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
