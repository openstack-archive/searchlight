Running Searchlight in containers
=================================

This contrib includes Dockerfile, docker-compose file and some configurations to run
Searchlight in Docker containers.

Requirements
------------

Follow guides in [1], [2] to install docker and docker-compose

Usage
-----

- Build docker image

::

    docker-compose -f docker-compose.example.yml build

- Adjust the authentication variables in your `docker-compose.example.yml`.

Example

::

    version: "3"
    services:
    searchlight-api:
        build: .
        ports:
        - 9393:9393
        environment:
        PROCESS: api
        AUTH_URL: http://192.168.53.31:5000/v3
        TRANSPORT_URL: rabbitmq://openstack:openstack@192.168.53.31
        SEARCHLIGHT_PASS: openstack
        ELASTICSEARCH_HOST: elasticsearch:9200

    searchlight-listener:
        build: .
        environment:
        PROCESS: listener
        AUTH_URL: http://192.168.53.31:5000/v3
        TRANSPORT_URL: rabbitmq://openstack:openstack@192.168.53.31
        SEARCHLIGHT_PASS: openstack
        ELASTICSEARCH_HOST: elasticsearch:9200

    elasticsearch:
        image: elasticsearch:5.6


- Running

::

    docker-compose -f docker-compose.example.yml up -

Environment Variables
---------------------

- TRANSPORT_URL: RabbitMQ URL. Example: rabbitmq://openstack:openstack@192.168.53.31
- REGION_NAME: Openstack Region Name. Example: RegionOne
- AUTH_URL: Keystone Auth URL. Example: http://192.168.53.31:5000
- SEARCHLIGHT_USER: Username of searchlight. Example: searchlight
- SEARCHLIGHT_PASS: Password of searchlight. Example: openstack
- PROJECT_NAME: Name of project for searchlight. Example: service
- DOMAIN_NAME: Name of domain for searchlight user and project: Example: default
- ELASTICSEARCH_HOST: Host and port of Elasticsearch. Example: 192.168.53.31:9200


References
----------

- [1] Install docker on Ubuntu: https://docs.docker.com/install/linux/docker-ce/ubuntu/
- [2] Install docker-compose: https://docs.docker.com/compose/install/
