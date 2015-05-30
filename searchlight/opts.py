import itertools

import searchlight.common.wsgi


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(searchlight.common.wsgi.bind_opts,
                         searchlight.common.wsgi.socket_opts,
                         searchlight.common.wsgi.eventlet_opts)),
        ('profiler',
         itertools.chain(searchlight.common.wsgi.profiler_opts)),
    ]
