#!/bin/bash

set -e

source ~/devstack/openrc admin admin

image_name="Admin Image Shared With Demo Project"
image_file=$( cd "$(dirname "$0")" ; pwd -P )"/"$(basename "$0")

(set -x; openstack image create --container-format bare --disk-format raw --file "$image_file" "$image_name")

image_id=`openstack image show "$image_name" -c id -f value`
demo_project_id=`openstack project show demo -c id -f value`

(set -x; glance member-create "$image_id" "$demo_project_id")

source ~/devstack/openrc admin demo

(set -x; glance member-update "$image_id" "$demo_project_id" accepted)

openstack image list

(set -x; glance member-list --image-id "$image_id")
