import setuptools


with open("README.rst", "r") as readme:
    long_description = readme.read()


setuptools.setup(
    name="yarsync",
    version="0.1-beta",
    author="Yaroslav Nikitenko",
    author_email="metst13@gmail.com",
    description="Yet Another Rsync is a file synchronization tool",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/ynikitenko/yarsync",
    project_urls = {
        # todo: add yarsync/docs
        # 'Documentation': "https://yarsync.readthedocs.io",
        'Source': 'https://github.com/ynikitenko/yarsync',
        'Tracker': 'https://github.com/ynikitenko/yarsync/issues',
    },
    keywords="distributed file synchronization, rsync, backup",
    packages=setuptools.find_packages(exclude=['tests', 'tests.*']),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console", 
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: Implementation :: PyPy",
        # "Topic :: Scientific/Engineering :: Information Analysis",
        # "Topic :: Software Development :: Libraries",
        # "License :: OSI Approved :: Apache Software License",
        # "Operating System :: OS Independent",
    ],
    # briefly about entry points in Russian
    # https://npm.mipt.ru/youtrack/articles/GENERAL-A-87/Использование-setuptools-в-Python
    # original docs (also brief):
    # https://setuptools.pypa.io/en/latest/userguide/entry_point.html
    entry_points={
        'console_scripts': [
            'yarsync = yarsync.yarsync:main',
        ]
    },
    python_requires='>=3.7',
)
