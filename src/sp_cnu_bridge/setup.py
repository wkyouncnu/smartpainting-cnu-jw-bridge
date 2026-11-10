from glob import glob
from setuptools import setup

package_name = "sp_cnu_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="CNU ANSL",
    maintainer_email="noreply@example.com",
    description="ZeroKey/Gazebo pose -> JW controller TCP bridge (GET_CUR_MPOS)",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "zerokey_sim = sp_cnu_bridge.zerokey_sim:main",
            "mpos_server = sp_cnu_bridge.mpos_server:main",
            "jw_mock_client = sp_cnu_bridge.jw_mock_client:main",
            "verify = sp_cnu_bridge.verify:main",
        ],
    },
)
