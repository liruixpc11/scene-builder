def auto_str(filter_attrs=None, auto_repr=True):
    filter_attrs = filter_attrs if filter_attrs else set()

    def _wrapper(cls):
        def __str__(self):
            return '%s(%s)' % (
                type(self).__name__,
                ', '.join('%s=%s' % item for item in vars(self).items() if item[0] not in filter_attrs)
            )

        cls.__str__ = __str__
        if auto_repr:
            cls.__repr__ = __str__
        return cls

    return _wrapper


length_to_mask_table = {
    '0': '0.0.0.0',
    '10': "255.192.0.0",
    '9': "255.128.0.0",
    '8': "255.0.0.0",
    '7': "254.0.0.0",
    '6': '252.0.0.0',
    '5': '248.0.0.0',
    '4': '240.0.0.0',
    '3': '224.0.0.0',
    '2': '192.0.0.0',
    '1': '128.0.0.0',
    '11': "255.224.0.0",
    '12': "255.240.0.0",
    '13': "255.248.0.0",
    '14': "255.252.0.0",
    '15': "255.254.0.0",
    '16': "255.255.0.0",
    '17': "255.255.128.0",
    '18': "255.255.192.0",
    '19': "255.255.224.0",
    '20': "255.255.240.0",
    '21': "255.255.248.0",
    '22': "255.255.252.0",
    '23': "255.255.254.0",
    '24': "255.255.255.0",
    '25': "255.255.255.128",
    '26': "255.255.255.192",
    '27': "255.255.255.224",
    '28': "255.255.255.240",
    '29': "255.255.255.248",
    '30': "255.255.255.252",
    '31': "255.255.255.254",
    '32': "255.255.255.255",
}


def net_prefix_len_to_mask(length):
    return
