#!/bin/bash
echo "Configure Searhclight"

searchlight_conf=/etc/searchlight/searchlight.conf

DOMAIN_NAME=${DOMAIN_NAME:-default}
PROJECT_NAME=${PROJECT_NAME:-service}
SEARCHLIGHT_USER=${SEARCHLIGHT_USER:-searchlight}
SEARCHLIGHT_PASS=${SEARCHLIGHT_PASS:-openstack}


crudini --set $searchlight_conf DEFAULT transport_url $TRANSPORT_URL

crudini --set $searchlight_conf service_credentials os_region_name $REGION_NAME
crudini --set $searchlight_conf service_credentials auth_url $AUTH_URL
crudini --set $searchlight_conf service_credentials username $SEARCHLIGHT_USER
crudini --set $searchlight_conf service_credentials password $SEARCHLIGHT_PASS
crudini --set $searchlight_conf service_credentials project_name $PROJECT_NAME
crudini --set $searchlight_conf service_credentials user_domain_name $DOMAIN_NAME
crudini --set $searchlight_conf service_credentials project_domain_name $DOMAIN_NAME

crudini --set $searchlight_conf keystone_authtoken auth_url $AUTH_URL
crudini --set $searchlight_conf keystone_authtoken auth_type password
crudini --set $searchlight_conf keystone_authtoken project_domain_name $DOMAIN_NAME
crudini --set $searchlight_conf keystone_authtoken user_domain_name $DOMAIN_NAME
crudini --set $searchlight_conf keystone_authtoken project_name $PROJECT_NAME
crudini --set $searchlight_conf keystone_authtoken username $SEARCHLIGHT_USER
crudini --set $searchlight_conf keystone_authtoken password $SEARCHLIGHT_PASS

crudini --set $searchlight_conf elasticsearch hosts $ELASTICSEARCH_HOST


if [ ! -f /opt/searchlight-synced ];then
    echo "Sync index to elasticsearch"
    while true;
    do
        curl -s $ELASTICSEARCH_HOST > /dev/null
        if [ $? -eq 0 ]; then
            echo "Starting sync index to elasticsearch"
            searchlight-manage index sync --force
            break
        fi
    done
    touch  /opt/searchlight-synced
fi

echo "Starting searchlight"

if [ ! -d /var/log/searchlight ]; then
    mkdir /var/log/searchlight
fi
searchlight-$PROCESS --log-file=/var/log/searchlight/searchlight-$PROCESS --config-file $searchlight_conf
