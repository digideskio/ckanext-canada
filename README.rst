ckanext-canada
==============

Government of Canada CKAN Extension - Extension à CKAN du Gouvernement du Canada

Features:

* Forms and Validation for GoC Metadata Schema

  * complete, see wet4-scheming branch for upcoming scheming version

* Batch import of data

  * merged into ckanapi

Installation:

* Use open-data fork of CKAN, branch canada-v2.1

From a clean database you must run::

    paster canada create-vocabularies
    ckanapi load organizations -I transitional_orgs.jsonl

Once to create the tag vocabularies and organizations this extension requires
before loading any data.


Plugins
-------

``canada_forms``
  dataset forms for data.gc.ca metadata schema

``canada_public``
  base and public facing data.gc.ca templates (requires
  ``canada_forms`` and ``wet_theme`` from
  `ckanext-wet-boew <https://github.com/open-data/ckanext-wet-boew>`_ )

``canada_internal``
  templates for internal site and registration (requires
  ``canada_forms`` and ``canada_public``)

``canada_package``
  package processing between CKAN and Solr


Requirements
------------

.. list-table:: Related projects, repositories, branches and CKAN plugins
 :header-rows: 1

 * - Project
   - Github group/repo
   - Branch
   - Plugins
 * - CKAN
   - `open-data/ckan <https://github.com/open-data/ckan>`_
   - canada-v2.1
   - * stats
 * - data.gc.ca extension
   - `open-data/ckanext-canada <https://github.com/open-data/ckanext-canada>`_
   - master
   - * canada_forms
     * canada_internal
     * canada_public
     * canada_package
 * - WET-BOEW theme
   - `open-data/ckanext-wet-boew <https://github.com/open-data/ckanext-wet-boew>`_
   - master
   - * wet_theme
 * - ckanapi
   - `ckan/ckanapi <https://github.com/ckan/ckanapi>`_
   - master
   - N/A
 * - ckanext-googleanalytics
   - `ofkn/ckanext-googleanalytics <https://github.com/okfn/ckanext-googleanalytics>`_
   - master
   - googleanalytics
 * - Recombinant tables extension
   - `open-data/ckanext-recombinant <https://github.com/open-data/ckanext-recombinant>`_
   - master
   - * recombinant


Configuration: development.ini or production.ini
------------------------------------------------

The CKAN ini file needs the following plugins for the registry server::

   ckan.plugins = stats googleanalytics canada_forms canada_internal canada_public canada_package wet_theme datastore recombinant

For the public server use only::

   ckan.plugins = stats googleanalytics canada_forms canada_public canada_package wet_theme

CKAN also needs to be able to find the licenses file for the license list
to be correctly populated::

   licenses_group_url = http://<ckan instance>/static/licenses.json

Users that don't belong to an Organization should not be allowed to create
datasets, without this setting the form will be presented but fail during
validation::

   ckan.auth.create_dataset_if_not_in_organization = false

We aren't using notification emails, so they need to be disabled::

   ckan.activity_streams_email_notifications = false

Additionally, we want to limit the search results page to 10 results per page::

   ckan.datasets_per_page = 10

To integrate Google Analytics::

   googleanalytics.id = UA-1010101-1 (your analytics account id)
   googleanalytics.account = Account name (i.e. data.gov.uk, see top level item at https://www.google.com/analytics)

For the public server, also set the Drupal portal URL::

   canada.portal_url = http://myserver.com

For the registry server set up recombinant configuration for ATI summaries::

   recombinant.tables = ckanext.canada:recombinant_tables.yaml


Configuration: Solr
----------------------

This extension uses a custom Solr schema based on the ckan 2.1 schema. You can find the schema in the root directory of the project.
Overwrite the default CKAN Solr schema with this one in order to enable search faceting over custom metadata fields.

You will need to rebuild your search index using::

   paster --plugin ckan search-index rebuild


Compiling the updated French localization strings
-------------------------------------------------

Each time you install or update this extension you need to install the
updated translations by running::

    bin/build-combined-ckan-mo.sh

This script overwrites the ckan French translations by combining it with
ours.

Linking with Drupal (Optional)
------------------------------

Data.gc.ca uses the Drupal web content management system to provide much of its content and to provide a means
for users to comment on and rate the data-sets found in the CKAN catalog. If using with Drupal, provide the database
connection string for the Drupal database in the CKAN configuration file::

    ckan.drupal.url =  postgresql://db_user:user_password/drupal_database

If this value is not defined, then the extension will not attempt to read from the Drupal database.

The installed Drupal site must have the opendata_package module enabled. In additional, 3 views are used by the
Drupal. Run the following SQL commands to create the necessary views in the Drupal database::

    create or replace view opendata_package_v as  select to_char(to_timestamp(c.changed::double precision),
        'YYYY-MM-DD'::text) AS changed, c.name, c.thread, f.comment_body_value, c.language, o.pkg_id FROM comment c
        JOIN field_data_comment_body f ON c.cid = f.entity_id
        JOIN opendata_package o ON (c.nid IN ( SELECT n.nid
        FROM node n
        WHERE n.nid = o.pkg_node_id and c.status = 1));

    create view opendata_package_rating_v as select avg(v.value)/25+1 as rating, p.pkg_id from opendata_package p
                 inner join votingapi_vote v on p.pkg_node_id = v.entity_id group by p.pkg_id;

    create or replace view opendata_package_count_v as select count(c.*), o.pkg_id from comment c
        inner join opendata_package o
        on o.pkg_node_id = c.nid and c.status = 1 group by o.pkg_id;

    alter view public.opendata_package_v owner to <db_user>;
    alter view public.opendata_package_rating_v owner to <db_user>;
    alter view public.opendata_package_count_v owner to <db_user>;

Substitute <db_user> with the appropriate SQL user account.
