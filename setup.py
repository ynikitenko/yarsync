import setuptools


with open("README.rst", "r") as readme:
    long_description = readme.read()


setuptools.setup(
    name="yarsync",
    version="0.2",
    author="Yaroslav Nikitenko",
    author_email="metst13@gmail.com",
    description="Yet Another Rsync is a file synchronization and backup tool",
    license="GPLv3",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/ynikitenko/yarsync",
    project_urls = {
        'Documentation': 'https://yarsync.readthedocs.io',
        'Source': 'https://github.com/ynikitenko/yarsync',
        'Tracker': 'https://github.com/ynikitenko/yarsync/issues',
    },
    keywords="distributed, file, synchronization, rsync, backup",
    packages=setuptools.find_packages(exclude=['tests', 'tests.*']),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console", 
        "Intended Audience :: End Users/Desktop",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: System :: Archiving",
        "Topic :: System :: Archiving :: Backup",
        "Topic :: System :: Archiving :: Mirroring",
        "Topic :: Utilities",
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
    python_requires='>=3.6',
)
