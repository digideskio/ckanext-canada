import logging
import json
import ckan.model as model
import webhelpers.feedgenerator

from ckan.lib.base import (BaseController, c, render, model, request, h, g,
    response, abort)
from ckan.logic import get_action, check_access, schema, NotAuthorized
from ckan.controllers.user import UserController
import ckan.new_authz as new_authz
from ckan.lib.helpers import Page, date_str_to_datetime, url
from ckan.controllers.feed import (FeedController, _package_search,
    _create_atom_id, _FixedAtom1Feed)
from ckan.lib import i18n
from ckan.lib.base import h, redirect
from ckan.controllers.package import PackageController
import ckan.lib.dictization.model_dictize as model_dictize

from ckanext.canada.helpers import normalize_strip_accents
from pylons.i18n import _
from pylons import config, session

from ckanapi import LocalCKAN, NotFound, NotAuthorized

class CanadaController(BaseController):
    def view_guidelines(self):
        return render('guidelines.html')

    def view_help(self):
        return render('help.html')

    def register(self, data=None, errors=None, error_summary=None):
        '''GET to display a form for registering a new user.
           or POST the form data to actually do the user registration.

           The bulk of this code is pulled directly from ckan/controlllers/user.py
        '''
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author,
                   'schema': schema.user_new_form_schema(),
                   'save': 'save' in request.params}

        try:
            check_access('user_create', context)
        except NotAuthorized:
            abort(401, _('Unauthorized to create a user'))

        if context['save'] and not data:
            uc = UserController()
            return uc._save_new(context)

        if c.user and not data:
            # #1799 Don't offer the registration form if already logged in
            return render('user/logout_first.html')

        data = data or {}
        errors = errors or {}
        error_summary = error_summary or {}

        vars = {'data': data, 'errors': errors, 'error_summary': error_summary}
        c.is_sysadmin = new_authz.is_sysadmin(c.user)
        c.form = render('user/new_user_form.html', extra_vars=vars)
        return render('user/new.html')


    def view_new_user(self):
        return render('newuser.html')

    def organization_index(self):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'for_view': True,
                   'with_private': False}

        data_dict = {'all_fields': True}

        try:
            check_access('site_read', context)
        except NotAuthorized:
            abort(401, _('Not authorized to see this page'))

        # pass user info to context as needed to view private datasets of
        # orgs correctly
        if c.userobj:
            context['user_id'] = c.userobj.id
            context['user_is_admin'] = c.userobj.sysadmin

        results = get_action('organization_list')(context, data_dict)

        def org_key(org):
            title = org['title'].split(' | ')[-1 if c.language == 'fr' else 0]
            return normalize_strip_accents(title)

        results.sort(key=org_key)

        c.page = Page(
            collection=results,
            page=request.params.get('page', 1),
            url=h.pager_url,
            items_per_page=1000
        )
        return render('organization/index.html')

    def logged_in(self):
        # we need to set the language via a redirect

        # Lang is not being retrieved properly by the Babel i18n lib in this redirect, so using
        # this clunky workaround for now.
        lang = session.pop('lang', None)
        if lang is None:
            came_from = request.params.get('came_from', '')
            if came_from.startswith('/fr'):
                lang = 'fr'

        session.save()

        # we need to set the language explicitly here or the flash
        # messages will not be translated.
        i18n.set_lang(lang)

        if c.user:
            is_new = False
            is_sysadmin = new_authz.is_sysadmin(c.user)

            # Retrieve information about the current user
            context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author,
                   'schema': schema.user_new_form_schema()}
            data_dict = {'id': c.user}

            user_dict = get_action('user_show')(context, data_dict)

            # This check is not needed (or correct) for sys admins
            if not is_sysadmin:

                # Get all organizations and all groups the user belongs to
                orgs_q = model.Session.query(model.Group) \
                    .filter(model.Group.is_organization == True) \
                    .filter(model.Group.state == 'active')
                q = model.Session.query(model.Member) \
                    .filter(model.Member.table_name == 'user') \
                    .filter(model.Member.table_id == user_dict['id'])

                group_ids = []
                for row in q.all():
                    group_ids.append(row.group_id)

                if not group_ids:
                    is_new = True
                else:
                    orgs_q = orgs_q.filter(model.Group.id.in_(group_ids))

                    orgs_list = model_dictize.group_list_dictize(orgs_q.all(), context)

                    if len(orgs_list) == 0:
                        is_new = True

            h.flash_success(_("<p><strong>Note</strong></p>"
                "<p>%s is now logged in</p>") %
                user_dict['display_name'], allow_html=True)

            if is_new:
                return h.redirect_to(controller='ckanext.canada.controller:CanadaController',
                                         action='view_new_user', locale=lang)
            else:
                return h.redirect_to(controller='package',
                    action='search', locale=lang)
        else:
            h.flash_error(_('Login failed. Bad username or password.'))
            return h.redirect_to(controller='user',
                action='login', locale=lang)

    def datatable(self, resource_name, resource_id):
        from ckanext.recombinant.tables import get_chromo
        t = get_chromo(resource_name)
        echo = int(request.params['sEcho'])
        search_text = unicode(request.params['sSearch'])
        offset = int(request.params['iDisplayStart'])
        limit = int(request.params['iDisplayLength'])
        sort_cols = int(request.params['iSortingCols'])
        if sort_cols:
            sort_by_num = int(request.params['iSortCol_0'])
            sort_order = 'desc' if request.params['sSortDir_0'] == 'desc' else 'asc'

        lc = LocalCKAN(username=c.user)

        unfiltered_response = lc.action.datastore_search(
            resource_id=resource_id,
            limit=1,
            )

        cols = [f['datastore_id'] for f in t['fields']]
        sort_str = ''
        if sort_cols:
            sort_str = cols[sort_by_num] + ' ' + sort_order

        response = lc.action.datastore_search(
            q=search_text,
            resource_id=resource_id,
            fields=cols,
            offset=offset,
            limit=limit,
            sort=sort_str)

        return json.dumps({
            'sEcho': echo,
            'iTotalRecords': unfiltered_response.get('total', 0),
            'iTotalDisplayRecords': response.get('total', 0),
            'aaData': [
                [row[colname] for colname in cols]
                for row in response['records']],
            })

class CanadaFeedController(FeedController):
    def general(self):
        data_dict, params = self._parse_url_params()
        data_dict['q'] = '*:*'

        item_count, results = _package_search(data_dict)

        navigation_urls = self._navigation_urls(params,
                                                item_count=item_count,
                                                limit=data_dict['rows'],
                                                controller='feed',
                                                action='general')

        feed_url = self._feed_url(params,
                                  controller='feed',
                                  action='general')

        alternate_url = self._alternate_url(params)

        return self.output_feed(results,
            feed_title=_(u'data.gc.ca Dataset Feed'),
            feed_description='',
            feed_link=alternate_url,
            feed_guid=_create_atom_id(
            u'/feeds/dataset.atom'),
            feed_url=feed_url,
            navigation_urls=navigation_urls)

    def output_feed(self, results, feed_title, feed_description,
                    feed_link, feed_url, navigation_urls, feed_guid):

        author_name = config.get('ckan.feeds.author_name', '').strip() or \
            config.get('ckan.site_id', '').strip()
        author_link = config.get('ckan.feeds.author_link', '').strip() or \
            config.get('ckan.site_url', '').strip()

        feed = _FixedAtom1Feed(
            title=feed_title,
            link=feed_link,
            description=feed_description,
            language=u'en',
            author_name=author_name,
            author_link=author_link,
            feed_guid=feed_guid,
            feed_url=feed_url,
            previous_page=navigation_urls['previous'],
            next_page=navigation_urls['next'],
            first_page=navigation_urls['first'],
            last_page=navigation_urls['last'],
        )

        if c.language == 'fr':
            def lx(x): return x + '_fra'
        else:
            def lx(x): return x

        for pkg in results:
            feed.add_item(
                title=pkg.get(lx('title'), ''),
                link=self.base_url + url(str(
                        '/api/action/package_show?id=%s' % pkg['name'])),
                description=pkg.get(lx('notes'), ''),
                updated=date_str_to_datetime(pkg.get('metadata_modified')),
                published=date_str_to_datetime(pkg.get('metadata_created')),
                unique_id=_create_atom_id(u'/dataset/%s' % pkg['id']),
                author_name=pkg.get('author', ''),
                author_email=pkg.get('author_email', ''),
                categories=''.join(e['value']
                    for e in pkg.get('extras',[])
                    if e['key'] == lx('keywords')).split(','),
                enclosure=webhelpers.feedgenerator.Enclosure(
                    self.base_url + url(str(
                        '/api/action/package_show?id=%s' % pkg['name'])),
                    unicode(len(json.dumps(pkg))),   # TODO fix this
                    u'application/json')
            )
        response.content_type = feed.mime_type
        return feed.writeString('utf-8')
        
class PublishController(PackageController):
    
    def _search_template(self, package_type):
        return 'publish/search.html'
        
    def _guess_package_type(self, expecting_name=False):
        # this is a bit unortodox, but this method allows us to conveniently alter the
        # search method without much code duplication.
        sysadmin = new_authz.is_sysadmin(c.user)
        if not sysadmin:
            abort(401, _('Not authorized to see this page'))
        
        #always set ready_to_publish to true for the publishing interface
        request.GET['ready_to_publish'] = u'true'
        return 'dataset'
        
    def publish(self):
        lc = LocalCKAN(username=c.user)
        
        publish_date = date_str_to_datetime(request.str_POST['publish_date']
            ).strftime("%Y-%m-%d %H:%M:%S")
        
        # get a list of package id's from the for POST data
        for key, package_id in request.str_POST.iteritems():
            if key == 'publish':
                old = lc.action.package_show(id=package_id)
                lc.call_action('package_update', dict(old,
                    portal_release_date=publish_date))
           
        #return us to the publishing interface
        url = h.url_for(controller='ckanext.canada.controller:PublishController',
                        action='search')
        redirect(url)
