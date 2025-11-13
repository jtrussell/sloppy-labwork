from django_hosts import patterns, host

host_patterns = patterns('',
                         host(r'', 'sloppy_labwork.urls', name='default'),
                         host(r'www', 'sloppy_labwork.urls', name='www'),
                         host(r'keychain', 'pmc.urls', name='keychain'),
                         )
