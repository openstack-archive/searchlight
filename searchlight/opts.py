import itertools

import searchlight.service


def list_opts():
    return [
        ('DEFAULT',
         itertools.chain(searchlight.service.OPTS))
    ]
