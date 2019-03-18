# Install and start **Searchlight** service

# To enable Searchlight services, add the following to localrc
# enable_plugin searchlight https://git.openstack.org/openstack/searchlight
# enable_service searchlight-api
# enable_service searchlight-listener

# stack.sh
# ---------
# install_searchlight
# configure_searchlight
# init_searchlight
# start_searchlight
# stop_searchlight
# cleanup_searchlight

# Save trace setting
XTRACE=$(set +o | grep xtrace)
set +o xtrace


# Defaults
# --------
# Set up default repos
SEARCHLIGHT_REPO=${SEARCHLIGHT_REPO:-${GIT_BASE}/openstack/searchlight.git}
SEARCHLIGHT_BRANCH=${SEARCHLIGHT_BRANCH:-master}

# Set up default paths
SEARCHLIGHT_BIN_DIR=$(get_python_exec_prefix)
SEARCHLIGHT_DIR=$DEST/searchlight
SEARCHLIGHT_CONF_DIR=/etc/searchlight
SEARCHLIGHT_STATE_PATH=${SEARCHLIGHT_STATE_PATH:=$DATA_DIR/searchlight}
SEARCHLIGHT_CONF=$SEARCHLIGHT_CONF_DIR/searchlight.conf
SEARCHLIGHT_LOG_DIR=/var/log/searchlight
SEARCHLIGHT_AUTH_CACHE_DIR=${SEARCHLIGHT_AUTH_CACHE_DIR:-/var/cache/searchlight}
SEARCHLIGHT_APIPASTE_CONF=$SEARCHLIGHT_CONF_DIR/api-paste.ini
SEARCHLIGHT_UWSGI_CONF=$SEARCHLIGHT_CONF_DIR/searchlight-uwsgi.ini
SEARCHLIGHT_UWSGI_APP=$SEARCHLIGHT_BIN_DIR/searchlight-api-wsgi

if is_service_enabled tls-proxy; then
    SEARCHLIGHT_SERVICE_PROTOCOL="https"
fi

# Public IP/Port Settings
SEARCHLIGHT_SERVICE_PROTOCOL=${SEARCHLIGHT_SERVICE_PROTOCOL:-$SERVICE_PROTOCOL}
SEARCHLIGHT_SERVICE_HOST=${SEARCHLIGHT_SERVICE_HOST:-$SERVICE_HOST}
SEARCHLIGHT_SERVICE_PORT=${SEARCHLIGHT_SERVICE_PORT:-9393}
SEARCHLIGHT_SERVICE_PORT_INT=${SEARCHLIGHT_SERVICE_PORT_INT:-19393}

ELASTICSEARCH_VERSION=${ELASTICSEARCH_VERSION:-2.3.4}
# Base URL for ElasticSearch 5.x and 6.x
ELASTICSEARCH_BASEURL=https://artifacts.elastic.co/downloads/elasticsearch
# Base URL for ElasticSearch 2.x
ELASTICSEARCH_BASEURL_LEGACY=https://download.elastic.co/elasticsearch/release/org/elasticsearch/distribution

# Helper Functions
# ----------------
function setup_colorized_logging_searchlight {
    local conf_file=$1
    local conf_section=$2
    local project_var=${3:-"project_name"}
    local user_var=${4:-"user_name"}

    setup_colorized_logging $conf_file $conf_section $project_var $user_var

    # Override the logging_context_format_string value chosen by
    # setup_colorized_logging.
    iniset $conf_file $conf_section logging_context_format_string "%(asctime)s.%(msecs)03d %(color)s%(levelname)s %(name)s [[01;36m%(request_id)s [00;36m%(user_identity)s%(color)s] [01;35m%(instance)s%(color)s%(message)s[00m"
}

# DevStack Plugin
# ---------------

# cleanup_searchlight - Remove residual data files, anything left over from previous
# runs that a clean run would need to clean up
function cleanup_searchlight {
    _stop_elasticsearch
    sudo rm -rf $SEARCHLIGHT_STATE_PATH $SEARCHLIGHT_AUTH_CACHE_DIR
    sudo rm -f $(apache_site_config_for searchlight_api)
}

# configure_searchlight - Set config files, create data dirs, etc
function configure_searchlight {
    [ ! -d $SEARCHLIGHT_CONF_DIR ] && sudo mkdir -m 755 -p $SEARCHLIGHT_CONF_DIR
    sudo chown $STACK_USER $SEARCHLIGHT_CONF_DIR

    [ ! -d $SEARCHLIGHT_LOG_DIR ] &&  sudo mkdir -m 755 -p $SEARCHLIGHT_LOG_DIR
    sudo chown $STACK_USER $SEARCHLIGHT_LOG_DIR

    # (Re)create ``searchlight.conf``
    rm -f $SEARCHLIGHT_CONF

    # General Configuration
    iniset_rpc_backend searchlight $SEARCHLIGHT_CONF DEFAULT

    iniset $SEARCHLIGHT_CONF DEFAULT debug $ENABLE_DEBUG_LOG_LEVEL
    iniset $SEARCHLIGHT_CONF DEFAULT state_path $SEARCHLIGHT_STATE_PATH

    # API Configuration
    sudo cp $SEARCHLIGHT_DIR/etc/api-paste.ini $SEARCHLIGHT_APIPASTE_CONF
    iniset $SEARCHLIGHT_CONF api public_endpoint $SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST/search

    # OpenStack users
    iniset $SEARCHLIGHT_CONF service_credentials auth_type password
    iniset $SEARCHLIGHT_CONF service_credentials username searchlight
    iniset $SEARCHLIGHT_CONF service_credentials user_domain_id default
    iniset $SEARCHLIGHT_CONF service_credentials project_domain_id default
    iniset $SEARCHLIGHT_CONF service_credentials password $SERVICE_PASSWORD
    iniset $SEARCHLIGHT_CONF service_credentials project_name $SERVICE_PROJECT_NAME
    iniset $SEARCHLIGHT_CONF service_credentials auth_url $KEYSTONE_SERVICE_URI
    iniset $SEARCHLIGHT_CONF service_credentials os_region_name $REGION_NAME

    # Keystone Middleware
    iniset $SEARCHLIGHT_CONF paste_deploy flavor keystone
    configure_auth_token_middleware $SEARCHLIGHT_CONF searchlight $SEARCHLIGHT_AUTH_CACHE_DIR

    # Oslo Concurrency
    iniset $SEARCHLIGHT_CONF oslo_concurrency lock_path "$SEARCHLIGHT_STATE_PATH"

    # TLS Proxy Configuration
    if is_service_enabled tls-proxy; then
        # Set the service port for a proxy to take the original
        iniset $SEARCHLIGHT_CONF api bind_port $SEARCHLIGHT_SERVICE_PORT_INT
    else
        iniset $SEARCHLIGHT_CONF api bind_port $SEARCHLIGHT_SERVICE_PORT
    fi

    # Logging Configuration
    if [ "$SYSLOG" != "False" ]; then
        iniset $SEARCHLIGHT_CONF DEFAULT use_syslog True
    fi

    # Format logging
    if [ "$LOG_COLOR" == "True" ] && [ "$SYSLOG" == "False" ]; then
        setup_colorized_logging_searchlight $SEARCHLIGHT_CONF DEFAULT "tenant" "user"
    fi

    # Plugin config - disable designate by default since it's not typically installed
    iniset $SEARCHLIGHT_CONF resource_plugin:os_designate_zone enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_designate_recordset enabled False

    # Plugin config - disable ironic by default since it's not typically installed
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_chassis enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_chassis notifications_topics_exchanges ironic_versioned_notifications,ironic
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_node enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_node notifications_topics_exchanges ironic_versioned_notifications,ironic
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_port enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_ironic_port notifications_topics_exchanges ironic_versioned_notifications,ironic

    # Plugin config - enable versioned notifications for flavor
    iniset $SEARCHLIGHT_CONF resource_plugin:os_nova_flavor enabled True
    iniset $SEARCHLIGHT_CONF resource_plugin:os_nova_flavor notifications_topics_exchanges versioned_notifications,nova

    iniset $SEARCHLIGHT_CONF resource_plugin:os_nova_server enabled True
    iniset $SEARCHLIGHT_CONF resource_plugin:os_nova_server notifications_topics_exchanges versioned_notifications,nova
    iniset $SEARCHLIGHT_CONF resource_plugin:os_nova_server use_versioned_notifications True

    # Plugin config - disable swift by default since it's not typically installed
    iniset $SEARCHLIGHT_CONF resource_plugin:os_swift_account enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_swift_container enabled False
    iniset $SEARCHLIGHT_CONF resource_plugin:os_swift_object enabled False

    # uWSGI configuration
    write_uwsgi_config "$SEARCHLIGHT_UWSGI_CONF" "$SEARCHLIGHT_UWSGI_APP" "/search"
}

# create_searchlight_accounts - Set up common required searchlight accounts

# Tenant               User       Roles
# ------------------------------------------------------------------
# service              searchlight  admin        # if enabled
function create_searchlight_accounts {
    if [[ "$ENABLED_SERVICES" =~ "searchlight-" ]]; then
        create_service_user "searchlight" "admin"

        if is_service_enabled searchlight-api; then
            get_or_create_service "searchlight" "search" "Searchlight Service"
            get_or_create_endpoint "search" \
                "$REGION_NAME" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST/search" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST/search" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST/search"
        fi
    fi
}

# init_searchlight - Initialize etc.
function init_searchlight {
    # Create cache dir
    sudo mkdir -p $SEARCHLIGHT_AUTH_CACHE_DIR
    sudo chown $STACK_USER $SEARCHLIGHT_AUTH_CACHE_DIR
    rm -f $SEARCHLIGHT_AUTH_CACHE_DIR/*

    _start_elasticsearch

    $SEARCHLIGHT_BIN_DIR/searchlight-manage --config-file $SEARCHLIGHT_CONF index sync --force
}

# Install Searchlight's requirements
# See https://elasticsearch-py.readthedocs.io/en/master/#compatibility
function _setup_searchlight_dev {
    setup_develop $SEARCHLIGHT_DIR
    if [[ $ELASTICSEARCH_VERSION =~ ^5 ]]; then
        echo "Installing python elasticsearch for ES 5.x"
        $REQUIREMENTS_DIR/.venv/bin/edit-constraints $REQUIREMENTS_DIR/upper-constraints.txt elasticsearch
        pip_install -U -r $SEARCHLIGHT_DIR/elasticsearch5.txt
    elif [[ $ELASTICSEARCH_VERSION =~ ^6 ]]; then
        echo "WARNING - Searchlight is not tested with ES 6.x!!!"
        # echo "Installing python elasticsearch for ES 6.x"
        # $REQUIREMENTS_DIR/.venv/bin/edit-constraints $REQUIREMENTS_DIR/upper-constraints.txt eleasticsearch
        # pip install -c $REQUIREMENTS_DIR/upper-constraints.txt -U -r $SEARCHLIGHT_DIR/elasticsearch6.txt
    fi
}

# install_searchlight - Collect source and prepare
function install_searchlight {
    git_clone $SEARCHLIGHT_REPO $SEARCHLIGHT_DIR $SEARCHLIGHT_BRANCH
    _setup_searchlight_dev
    _download_elasticsearch
    _install_elasticsearch
    pip_install uwsgi
}

# install_searchlightclient - Collect source and prepare
function install_searchlightclient {
    git_clone $SEARCHLIGHTCLIENT_REPO $SEARCHLIGHTCLIENT_DIR $SEARCHLIGHTCLIENT_BRANCH
    setup_develop $SEARCHLIGHTCLIENT_DIR
}

# start_searchlight - Start running processes, including screen
function start_searchlight {
    if is_service_enabled searchlight-api; then
        run_process searchlight-api "$SEARCHLIGHT_BIN_DIR/uwsgi --ini $SEARCHLIGHT_UWSGI_CONF"
    fi
    if is_service_enabled searchlight-listener; then
        run_process searchlight-listener "$SEARCHLIGHT_BIN_DIR/searchlight-listener --config-file $SEARCHLIGHT_CONF"
    fi
}

# stop_searchlight - Stop running processes
function stop_searchlight {
    # Kill the searchlight screen windows
    stop_process searchlight-api
    stop_process searchlight-listener
    remove_uwsgi_config "$SEARCHLIGHT_UWSGI_CONF" "$SEARCHLIGHT_UWSGI_APP"
}


###############
# ELASTICSEARCH
# Moving this here because the devstack team has determined that only
# services supporting devstack core projects should live in devstack

function _wget_elasticsearch {
    local baseurl=${1}
    local file=${2}
    if [ ! -f ${FILES}/${file} ]; then
        wget ${baseurl}/${file} -O ${FILES}/${file}
    fi

    if [ ! -f ${FILES}/${file}.sha1 ]; then
        # Starting with 2.0.0, sha1 files dropped the .txt extension and changed
        # the format slightly; need the leading spaces to comply with sha1sum
        ( wget ${baseurl}/${file}.sha1 -O ${FILES}/${file}.sha1 &&
          echo "  ${file}" >> ${FILES}/${file}.sha1 )
    fi

    pushd ${FILES};  sha1sum ${file} > ${file}.sha1.gen;  popd

    if ! diff ${FILES}/${file}.sha1.gen ${FILES}/${file}.sha1; then
        echo "Invalid elasticsearch download. Could not install."
        return 1
    else
        echo "SHA1 for ${file} matches downloaded ${FILES}/${file}.sha1"
    fi
    return 0
}

function _download_elasticsearch {
    if is_ubuntu; then
        arch="deb"
    elif is_fedora; then
        arch="rpm"
    else
        echo "Unknown architecture; can't download ElasticSearch"
    fi
    ELASTICSEARCH_FILENAME=elasticsearch-${ELASTICSEARCH_VERSION}.${arch}

    if [[ $ELASTICSEARCH_VERSION =~ ^2 ]]; then
        ELASTICSEARCH_URL=${ELASTICSEARCH_BASEURL_LEGACY}/${arch}/elasticsearch/${ELASTICSEARCH_VERSION}
    elif [[ $ELASTICSEARCH_VERSION =~ ^5 ]]; then
        ELASTICSEARCH_URL=${ELASTICSEARCH_BASEURL}
    else
        echo "Current Searchlight only supports ElasticSearch 2.x and 5.x"
    fi
    echo "Downloading ElasticSearch $ELASTICSEARCH_VERSION"
    echo "ElasticSearch URL is $ELASTICSEARCH_URL"
    _wget_elasticsearch $ELASTICSEARCH_URL $ELASTICSEARCH_FILENAME
}

function _check_elasticsearch_ready {
    # poll elasticsearch to see if it's started
    if ! wait_for_service 30 http://localhost:9200; then
        die $LINENO "Maximum timeout reached. Could not connect to ElasticSearch"
    fi
}

function _start_elasticsearch {
    echo "Starting elasticsearch"
    if is_ubuntu; then
        sudo /etc/init.d/elasticsearch start
        _check_elasticsearch_ready
    elif is_fedora; then
        sudo /bin/systemctl start elasticsearch.service
        _check_elasticsearch_ready
    else
        echo "Unsupported architecture... Can not start elasticsearch."
    fi
}

function _stop_elasticsearch {
    echo "Stopping elasticsearch"
    if is_ubuntu; then
        sudo /etc/init.d/elasticsearch stop
    elif is_fedora; then
        sudo /bin/systemctl stop elasticsearch.service
    else
        echo "Unsupported architecture...can not stop elasticsearch."
    fi
}

function _install_elasticsearch {
    # echo "Installing elasticsearch"
    # pip_install_gr elasticsearch
    if is_package_installed elasticsearch; then
        echo "Note: elasticsearch was already installed."
        return
    fi
    if is_ubuntu; then
        if [[ ${DISTRO} == "bionic" ]]; then
            is_package_installed openjdk-8-jdk-headless || install_package openjdk-8-jdk-headless
        else
            is_package_installed default-jdk-headless || install_package default-jdk-headless
        fi
        sudo dpkg -i ${FILES}/elasticsearch-${ELASTICSEARCH_VERSION}.deb
        sudo update-rc.d elasticsearch defaults 95 10
    elif is_fedora; then
        is_package_installed java-1.8.0-openjdk-headless || install_package java-1.8.0-openjdk-headless
        yum_install ${FILES}/elasticsearch-${ELASTICSEARCH_VERSION}.rpm
        sudo /bin/systemctl daemon-reload
        sudo /bin/systemctl enable elasticsearch.service
    else
        echo "Unsupported install of elasticsearch on this architecture."
    fi
}

function _uninstall_elasticsearch {
    echo "Uninstalling elasticsearch"
    if is_package_installed elasticsearch; then
        if is_ubuntu; then
            sudo apt-get purge elasticsearch
        elif is_fedora; then
            sudo yum remove elasticsearch
        else
            echo "Unsupported install of elasticsearch on this architecture."
        fi
    fi
}

#
# END OF ELASTICSEARCH
######################


# check for service enabled
if is_service_enabled searchlight; then

    if [[ "$1" == "source" ]]; then
        # Initial source of lib script
        source $TOP_DIR/lib/searchlight
    fi

    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Searchlight"
        install_searchlight

        echo_summary "Installing Searchlight client"
        install_searchlightclient
    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        echo_summary "Configuring Searchlight"
        configure_searchlight

        if is_service_enabled key; then
            echo_summary "Creating Searchlight Keystone Accounts"
            create_searchlight_accounts
        fi

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        echo_summary "Initializing Searchlight"
        init_searchlight

        echo_summary "Starting Searchlight"
        start_searchlight
    fi

    if [[ "$1" == "unstack" ]]; then
        stop_searchlight
    fi

    if [[ "$1" == "clean" ]]; then
        echo_summary "Cleaning Searchlight"
        cleanup_searchlight
    fi
fi

# Restore xtrace
$XTRACE
