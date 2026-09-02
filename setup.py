from glob import glob

from setuptools import find_packages, setup


PACKAGE_NAME = "buddy_robot"


setup(
    name=PACKAGE_NAME,
    version="0.1.0",
    packages=find_packages(exclude=("tests",)),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{PACKAGE_NAME}"]),
        (f"share/{PACKAGE_NAME}", ["package.xml"]),
        (f"share/{PACKAGE_NAME}/launch", glob("launch/*.launch.py")),
        (f"share/{PACKAGE_NAME}/urdf", glob("urdf/*.urdf.xacro")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Buddy maintainers",
    maintainer_email="maintainer@example.com",
    description="ROS 2 nodes for the Buddy robot car.",
    license="Proprietary",
    entry_points={
        "console_scripts": [
            "distance_node = buddy_ros.distance_node:main",
            "follow_node = buddy_ros.follow_node:main",
            "motor_node = buddy_ros.motor_node:main",
            "odometry_node = buddy_ros.odometry_node:main",
            "person_node = buddy_ros.person_node:main",
            "power_node = buddy_ros.power_node:main",
            "reaction_node = buddy_ros.reaction_node:main",
        ],
    },
)
