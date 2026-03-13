from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="lexington_inventory",
    version="0.1.0",
    description="Lexington Inventory Monitor — real-time stock tracking, cycle count management, low-stock alerts, and supplier integration for Welchwyse",
    author="Welchwyse",
    author_email="admin@welchwyse.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
