import itertools

import searchlight.common.wsgi
import searchlight.common.property_utils
import searchlight.common.config


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(searchlight.common.wsgi.bind_opts,
                         searchlight.common.wsgi.socket_opts,
                         searchlight.common.wsgi.eventlet_opts,
                         searchlight.common.property_utils.property_opts,
                         searchlight.common.config.common_opts)),
        ('paste_deploy',
         searchlight.common.config.paste_deploy_opts),
        ('profiler',
         searchlight.common.wsgi.profiler_opts),
    ]
