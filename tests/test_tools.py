from netbox_netdev_inventory.tools import (
    is_macaddr, macaddr_to_int
)

class TestTools():

    def test_macaddr_to_int(self):
        assert macaddr_to_int('00:00:FF:00:00:FF') == 4278190335

    def test_macaddr_to_int_is_Null(self):
        assert macaddr_to_int(None) == 0

    def test_is_macaddr_true1(self):
        assert is_macaddr('00.11:22:AA:44.ff') == True

    def test_is_macaddr_true2(self):
        assert is_macaddr('001122AA44cc') == True

    def test_is_macaddr_false1(self):
        assert is_macaddr('00:11:22:AA:44') == False

    def test_is_macaddr_false2(self):
        assert is_macaddr('00:11:22:AA:44:Gg') == False
