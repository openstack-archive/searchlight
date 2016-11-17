#!/bin/bash -xe

# This script will be run by OpenStack CI before unit tests are run,
# it sets up the test system as needed.
# Developer should setup their test systems in a similar way.

# This setup needs to be run by a user that can run sudo.

sudo apt-get update
sudo apt-get install -y default-jre
wget https://download.elastic.co/elasticsearch/elasticsearch/elasticsearch-1.7.0.deb
sudo dpkg -i elasticsearch-1.7.0.deb
# Make 'elasticsearch' binary callable from within functional tests
sudo ln -s /usr/share/elasticsearch/bin/elasticsearch /usr/local/bin/elasticsearch
