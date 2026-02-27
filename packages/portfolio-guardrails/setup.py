from setuptools import setup, find_packages

setup(
    name="portfolio-guardrails",
    version="0.1.0",
    description="Production-ready portfolio risk guardrails for LangChain financial agents",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "langchain-core>=0.1.0",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Office/Business :: Financial :: Investment",
        "Programming Language :: Python :: 3",
    ],
)
