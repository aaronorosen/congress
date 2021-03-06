# Copyright (c) 2014 VMware, Inc. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import congress.dse.deepsix as deepsix


def d6service(name, keys, inbox, datapath, args):
    return TableModel(name, keys, inbox=inbox, dataPath=datapath, **args)


class TableModel(deepsix.deepSix):
    """Model for handling API requests about Tables."""
    def __init__(self, name, keys, inbox=None, dataPath=None,
                 policy_engine=None):
        super(TableModel, self).__init__(name, keys, inbox=inbox,
                                         dataPath=dataPath)
        self.engine = policy_engine

    def get_item(self, id_, context=None):
        """Retrieve item with id id_ from model.

        Args:
            id_: The ID of the item to retrieve
            context: Key-values providing frame of reference of request

        Returns:
             The matching item or None if item with id_ does not exist.
        """
        # ds_id is a policy name
        if context['ds_id'] in self.engine.theory:
            if id_ in self.engine.theory[context['ds_id']].tablenames():
                return {'id': id_}
            else:
                return None
        # ds_id is a datasource name
        fullname = context['ds_id'] + ":" + id_
        if fullname not in self.engine.theory[self.engine.theory.DATABASE]:
            return None
        return {'id': id_}

    def get_items(self, context=None):
        """Get items in model.

        Args:
            context: Key-values providing frame of reference of request

        Returns: A sequence of (id, item) for all items in model.
        """
        if context['ds_id'] in self.engine.theory:
            return [(x, {'id': x})
                    for x in self.engine.theory[context['ds_id']].tablenames()]
        # technically we're only returning the tables for this data source
        #   that the policy engine is subscribed to.
        ds = context['ds_id']
        result = []
        for x in self.engine.theory[self.engine.theory.DATABASE]:
            if x.startswith(ds):
                actual_id = x[len(ds) + 1:]
                result.append((actual_id, {'id': actual_id}))
        return result

    # Tables can only be created/updated/deleted by writing policy
    #   or by adding new data sources.  Once we have internal data sources
    #   we need to implement all of these.

    # def add_item(self, item, id_=None, context=None):
    #     """Add item to model.

    #     Args:
    #         item: The item to add to the model
    #         id_: The ID of the item, or None if an ID should be generated
    #         context: Key-values providing frame of reference of request

    #     Returns:
    #          Tuple of (ID, newly_created_item)

    #     Raises:
    #         KeyError: ID already exists.
    #     """


    # def update_item(self, id_, item, context=None):
    #     """Update item with id_ with new data.

    #     Args:
    #         id_: The ID of the item to be updated
    #         item: The new item
    #         context: Key-values providing frame of reference of request

    #     Returns:
    #          The updated item.

    #     Raises:
    #         KeyError: Item with specified id_ not present.
    #     """
    #     # currently a noop since the owner_id cannot be changed
    #     if id_ not in self.items:
    #         raise KeyError("Cannot update item with ID '%s': "
    #                        "ID does not exist")
    #     return item

    # def delete_item(self, id_, context=None):
        # """Remove item from model.

        # Args:
        #     id_: The ID of the item to be removed
        #     context: Key-values providing frame of reference of request

        # Returns:
        #      The removed item.

        # Raises:
        #     KeyError: Item with specified id_ not present.
        # """
