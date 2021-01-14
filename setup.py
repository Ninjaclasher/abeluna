from setuptools import find_packages, setup

with open('README.md') as f:
    readme = f.read()

setup(
    name='abeluna',
    version='1.0.4',
    entry_points={
        'gui_scripts': [
            'abeluna = abeluna.main:main',
        ],
    },
    author='Evan Zhang',
    install_requires=['pygobject', 'humanize', 'icalendar', 'caldav'],
    include_package_data=True,
    description='A simple GUI to-do/task manager with CalDAV support.',
    long_description=readme,
    long_description_content_type='text/markdown',
    url='https://github.com/Ninjaclasher/abeluna',
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: X11 Applications :: GTK',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
)
