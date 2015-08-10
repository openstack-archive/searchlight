# Install and start **Searchlight** service

# To enable Searchlight services, add the following to localrc
# enable_plugin searchlight http://git.openstack.org/openstack/searchlight
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
SEARCHLIGHT_CONF=$SEARCHLIGHT_CONF_DIR/searchlight-api.conf
SEARCHLIGHT_LOG_DIR=/var/log/searchlight
SEARCHLIGHT_AUTH_CACHE_DIR=${SEARCHLIGHT_AUTH_CACHE_DIR:-/var/cache/searchlight}
SEARCHLIGHT_APIPASTE_CONF=$SEARCHLIGHT_CONF_DIR/searchlight-api-paste.ini

# Public IP/Port Settings
SEARCHLIGHT_SERVICE_PROTOCOL=${SEARCHLIGHT_SERVICE_PROTOCOL:-$SERVICE_PROTOCOL}
SEARCHLIGHT_SERVICE_HOST=${SEARCHLIGHT_SERVICE_HOST:-$SERVICE_HOST}
SEARCHLIGHT_SERVICE_PORT=${SEARCHLIGHT_SERVICE_PORT:-9393}
SEARCHLIGHT_SERVICE_PORT_INT=${SEARCHLIGHT_SERVICE_PORT_INT:-19393}


# Tell Tempest this project is present
TEMPEST_SERVICES+=,searchlight

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
    ${TOP_DIR}/pkg/elasticsearch.sh stop
    sudo rm -rf $SEARCHLIGHT_STATE_PATH $SEARCHLIGHT_AUTH_CACHE_DIR
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
    iniset $SEARCHLIGHT_CONF DEFAULT verbose True
    iniset $SEARCHLIGHT_CONF DEFAULT state_path $SEARCHLIGHT_STATE_PATH

    # Install the policy file for the API server
    cp $SEARCHLIGHT_DIR/etc/policy.json $SEARCHLIGHT_CONF_DIR/policy.json
    iniset $SEARCHLIGHT_CONF DEFAULT policy_file $SEARCHLIGHT_CONF_DIR/policy.json

    # API Configuration
    sudo cp $SEARCHLIGHT_DIR/etc/searchlight-api-paste.ini $SEARCHLIGHT_APIPASTE_CONF
    iniset $SEARCHLIGHT_CONF DEFAULT public_endpoint $SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST:$SEARCHLIGHT_SERVICE_PORT/

    # OpenStack users
    iniset $SEARCHLIGHT_CONF service_credentials os_username searchlight
    iniset $SEARCHLIGHT_CONF service_credentials os_tenant_name $SERVICE_TENANT_NAME
    iniset $SEARCHLIGHT_CONF service_credentials os_password $SERVICE_PASSWORD
    iniset $SEARCHLIGHT_CONF service_credentials os_auth_url $KEYSTONE_AUTH_URI/v2.0

    # Keystone Middleware
    iniset $SEARCHLIGHT_CONF paste_deploy flavor keystone
    configure_auth_token_middleware $SEARCHLIGHT_CONF searchlight $SEARCHLIGHT_AUTH_CACHE_DIR

    # Oslo Concurrency
    iniset $SEARCHLIGHT_CONF oslo_concurrency lock_path "$SEARCHLIGHT_STATE_PATH"

    # TLS Proxy Configuration
    if is_service_enabled tls-proxy; then
        # Set the service port for a proxy to take the original
        iniset $SEARCHLIGHT_CONF service:api bind_port $SEARCHLIGHT_SERVICE_PORT_INT
    else
        iniset $SEARCHLIGHT_CONF service:api bind_port $SEARCHLIGHT_SERVICE_PORT
    fi

    # Logging Configuration
    if [ "$SYSLOG" != "False" ]; then
        iniset $SEARCHLIGHT_CONF DEFAULT use_syslog True
    fi

    # Format logging
    if [ "$LOG_COLOR" == "True" ] && [ "$SYSLOG" == "False" ]; then
        setup_colorized_logging_searchlight $SEARCHLIGHT_CONF DEFAULT "tenant" "user"
    fi
}

# create_searchlight_accounts - Set up common required searchlight accounts

# Tenant               User       Roles
# ------------------------------------------------------------------
# service              searchlight  admin        # if enabled
function create_searchlight_accounts {
    if [[ "$ENABLED_SERVICES" =~ "searchlight-" ]]; then
        create_service_user "searchlight" "admin"

        if is_service_enabled searchlight-api && [[ "$KEYSTONE_CATALOG_BACKEND" = 'sql' ]]; then
            local searchlight_service=$(get_or_create_service "searchlight" \
                "search" "Searchlight Service")
            get_or_create_endpoint $searchlight_service \
                "$REGION_NAME" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST:$SEARCHLIGHT_SERVICE_PORT/" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST:$SEARCHLIGHT_SERVICE_PORT/" \
                "$SEARCHLIGHT_SERVICE_PROTOCOL://$SEARCHLIGHT_SERVICE_HOST:$SEARCHLIGHT_SERVICE_PORT/"
        fi
    fi
}

# init_searchlight - Initialize etc.
function init_searchlight {
    # Create cache dir
    sudo mkdir -p $SEARCHLIGHT_AUTH_CACHE_DIR
    sudo chown $STACK_USER $SEARCHLIGHT_AUTH_CACHE_DIR
    rm -f $SEARCHLIGHT_AUTH_CACHE_DIR/*

    ${TOP_DIR}/pkg/elasticsearch.sh start

    $SEARCHLIGHT_BIN_DIR/searchlight-manage --config-file $SEARCHLIGHT_CONF index sync
}

# install_searchlight - Collect source and prepare
function install_searchlight {
    git_clone $SEARCHLIGHT_REPO $SEARCHLIGHT_DIR $SEARCHLIGHT_BRANCH
    setup_develop $SEARCHLIGHT_DIR

    ${TOP_DIR}/pkg/elasticsearch.sh download
    ${TOP_DIR}/pkg/elasticsearch.sh install
}

# start_searchlight - Start running processes, including screen
function start_searchlight {
    if is_service_enabled searchlight-api; then
        run_process searchlight-api "$SEARCHLIGHT_BIN_DIR/searchlight-api --config-file $SEARCHLIGHT_CONF"

        # Start proxies if enabled
        if is_service_enabled searchlight-api && is_service_enabled tls-proxy; then
            start_tls_proxy '*' $SEARCHLIGHT_SERVICE_PORT $SEARCHLIGHT_SERVICE_HOST $SEARCHLIGHT_SERVICE_PORT_INT &
        fi
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
}

# check for service enabled
if is_service_enabled searchlight; then

    if [[ "$1" == "source" ]]; then
        # Initial source of lib script
        source $TOP_DIR/lib/searchlight
    fi

    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installing Searchlight"
        install_searchlight
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
