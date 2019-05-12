from __future__ import unicode_literals
import frappe
import os
import six

from frappe.utils import encode

class data_import_wrapper():
    def __init__(self, attachment_name):
        tpl_data_import = frappe._dict({
            'doctype': u'Data Import',
            'action': u'Insert new records',
            'docstatus': 0,
            'ignore_encoding_errors': 1,
            'insert_new': 1,
            'no_email': 1,
            'only_update': 1,
            'overwrite': 0,
            'reference_doctype': u'Payment Entry',
            'show_only_errors': 0,
            'skip_errors': 1,
            'submit_after_import': 1
        })
        data_import_doc = frappe.get_doc(tpl_data_import)
        self.new_doc = data_import_doc.insert()
        self.attach_doc = frappe.get_doc("File", attachment_name)
        self.attach_doc.attached_to_doctype =  data_import_doc.doctype
        self.attach_doc.attached_to_name= data_import_doc.name
        self.attach_doc.insert()

        self.import_log = []
        self.error_flag = False

    def set_total(self, total):
        self.total = total
    def publish_progress(self, achieved, message, reload=False):
        if self.new_doc:
            frappe.publish_realtime("data_import_progress", {"progress": str(int(100.0*achieved/self.total)),
                "data_import": self.new_doc.name,"message": message, "reload": reload}, user=frappe.session.user)

    def log_info(self, titel, message, link=None, color="green", on_top=False):
        log_entry = {
            "row": None,
            "title":'%s' % (titel),
            "message": '%s' % (message),
            "link": link,
            "indicator": color
        }
        if on_top:
            self.import_log.insert(0,log_entry)
        else:
            self.import_log.append(log_entry)

    def log_successful(self, index, doc):
        self.import_log.append({
            "row": index,
            "title":'Inserted row for "%s"' % (getlink(doc.doctype, doc.name)),
            "message": "Document successfully saved",
            "link": get_absolute_url(doc.doctype, doc.name),
            "indicator": "green"
        })
    def log_duplicate(self, index, doc):
        self.import_log.append({
            "row": index,
            "title":'Duplicate of "%s"' % (getlink(doc.doctype, doc.name)),
            "message": '%s already exists' % (doc.doctype),
            "link": get_absolute_url(doc.doctype, doc.name),
            "indicator": "green"
        })
    def log_skip(self, index, details):
        self.import_log.append({
            "row": index,
            "title":'Skiped row %s ' % (index),
            "link": None,
            "message": 'Skiped row because %s ' % (details),
            "indicator": "green"})
    def log_error(self, index, details, e, stop=False):
        self.error_flag = True
        err_msg = '<p class="border-bottom small">{}</p>'.format(cstr(e))

        error_trace = frappe.get_traceback()
        if error_trace:
            error_log_doc = frappe.log_error(error_trace)
            error_link = get_absolute_url("Error Log", error_log_doc.name)
        else:
            error_link = None

        self.import_log.append({
            "row": index,
            "title":'Error for row %s ' % (index),
            "link":error_link,
            "message": err_msg,
            "indicator": "red"})
        self.import_end(stop)
    def import_end(self, critical=False):
        log_message = {"messages": self.import_log, "error": self.error_flag}
        if self.new_doc:
            self.new_doc.log_details = json.dumps(log_message)
            if critical:
                self.new_doc.import_status = "Failed"
            elif self.error_flag:
                self.new_doc.import_status = "Partially Successful"
            else:
                self.new_doc.import_status = "Successful"
            self.new_doc.submit()
            #frappe.db.commit()
            # Prevent file/encoding error
            frappe.db.set_value(self.new_doc.doctype, self.new_doc.name, "import_file", self.attach_doc.file_url)
            frappe.db.commit()

class template_import():
    def __init__(self):
        file_dir = os.path.dirname(__file__)
        file_path = os.path.join(file_dir, "template_config.json")

        if six.PY2:
          with open(encode(file_path)) as f:
            content = f.read()
        else:
          with io.open(encode(file_path), mode='rb') as f:
            content = f.read()
            content = content.decode()

        self.tpl_config = frappe.json.loads(content)

    def get_Content(self):
        return self.tpl_config


def test():
    tpl_process = template_import()
    tpl_config = tpl_process.get_Content()
    print(tpl_config)
    print("-------------------")
    for name, i in six.iteritems(tpl_config):
        tpl_config[name]['field_index'] = True
        tpl_config[name]['field_reg'] = True
    print(tpl_config)
