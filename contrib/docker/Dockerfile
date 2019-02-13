FROM ubuntu:18.04
MAINTAINER saphi070@gmail.com

RUN apt update
RUN apt install -y python-dev libssl-dev python-pip libxml2-dev \
                   libxslt-dev git git-review libffi-dev gettext \
                   python-tox python-memcache crudini

### Clone searchlight source code
RUN apt install wget -y
WORKDIR /home
RUN git clone https://git.openstack.org/openstack/searchlight
WORKDIR /home/searchlight

### Install Searchlight
RUN pip install -r requirements.txt
RUN pip install -r elasticsearch5.txt
RUN python setup.py install
RUN oslo-config-generator --config-file etc/oslo-config-generator/searchlight.conf
RUN cp etc/searchlight.conf.sample /etc/searchlight/searchlight.conf
RUN mkdir /etc/searchlight/

### Copy Configure files
RUN cp etc/api-paste.ini /etc/searchlight/
# COPY searchlight.conf /etc/searchlight/
COPY entrypoint.sh /home/
RUN chmod 775 /home/entrypoint.sh
EXPOSE 9393
WORKDIR /home
ENTRYPOINT ["./entrypoint.sh"]
