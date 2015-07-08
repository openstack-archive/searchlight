======================
 Enabling in Devstack
======================

1. Download DevStack

2. Add this repo as an external repository::

     > cat local.conf
     [[local|localrc]]
     enable_plugin searchlight https://github.com/openstack/searchlight
     enable_service searchlight-api
     enable_service searchlight-listener

3. Run ``stack.sh``


.. note::
   This installs a headless JRE. If you are working on a desktop based OS
   (such as Ubuntu 14.04), this may cause tools like pycharms to no longer
   launch. You can switch between JREs and back: to a headed JRE version using:
   "sudo update-alternatives --config java".
