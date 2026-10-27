"""SDN controllers (PHASE8_PLAN section 17): a controller's flow tables read, checked and changed
through Mercury, the way device configuration is.

`modules/sdn/drivers/` holds the controller drivers: one interface (`drivers.base`), one
registry by kind (`drivers.DRIVERS`), and each controller's translation of its own REST API
into the one shape. Nothing here names an address, a lab or a topology: a controller's URL and
credentials are the operator's values in Settings (17.1 S2).
"""
