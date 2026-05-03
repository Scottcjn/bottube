#!/usr/bin/env python3
"""Setup script for bottube-verify, the open-source provenance verifier."""

from setuptools import setup

with open("VERIFIER_README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="bottube-verify",
    version="0.5.0",
    description=(
        "Open-source verifier for BoTTube on-chain provenance. "
        "Cryptographically prove any video on bottube.ai is correctly "
        "anchored on RustChain — no admin access, no special node required."
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Scott Boudreaux (Elyan Labs)",
    author_email="scott@elyanlabs.ai",
    url="https://github.com/Scottcjn/bottube",
    license="MIT",
    py_modules=["bottube_verify_provenance"],
    python_requires=">=3.9",
    # Phase 11.23: PyNaCl is required for v3 manifest signatures.
    # Older v1+v2 verification still works without it (stdlib-only)
    # but the verifier will refuse to PASS a v3 anchor without
    # actually verifying the Ed25519 signature.
    install_requires=["PyNaCl>=1.5.0"],
    entry_points={
        "console_scripts": [
            "bottube-verify=bottube_verify_provenance:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet",
        "Topic :: Security :: Cryptography",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=["provenance", "merkle", "ergo", "rustchain", "bottube", "verifier"],
    project_urls={
        "Source": "https://github.com/Scottcjn/bottube",
        "Anchor Ledger": "https://bottube.ai/anchors",
        "Federation Spec": "https://bottube.ai/federation",
    },
)
