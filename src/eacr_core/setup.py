from setuptools import find_packages, setup


setup(
    name="eacr_core",
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/eacr_core"]),
        ("share/eacr_core", ["package.xml"]),
    ],
    install_requires=[],
    zip_safe=True,
)
