# -*- coding: utf-8 -*-
# Copyright (c) 2017-2019, libracore (https://www.libracore.com) and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document
import cgi          # used to escape xml content

class AbacusExportFile(Document):
    def submit(self):
        self.get_transactions()
        return
        
    # find all transactions, add the to references and mark as collected
    def get_transactions(self):
        # get all documents
        document_query = """SELECT 
                    "Sales Invoice" AS `dt`,
                    `tabSales Invoice`.`name` AS `dn`
                FROM `tabSales Invoice`
                WHERE
                    `tabSales Invoice`.`posting_date` >= '{start_date}'
                    AND `tabSales Invoice`.`posting_date` <= '{end_date}'
                    AND `tabSales Invoice`.`docstatus` = 1
                    AND `tabSales Invoice`.`exported_to_abacus` = 0
                    AND `tabSales Invoice`.`company` = '{company}'
                UNION SELECT 
                    "Purchase Invoice" AS `dt`,
                    `tabPurchase Invoice`.`name` AS `dn`
                FROM `tabPurchase Invoice`
                WHERE
                    `tabPurchase Invoice`.`posting_date` >= '{start_date}'
                    AND `tabPurchase Invoice`.`posting_date` <= '{end_date}'
                    AND `tabPurchase Invoice`.`docstatus` = 1
                    AND `tabPurchase Invoice`.`exported_to_abacus` = 0
                    AND `tabPurchase Invoice`.`company` = '{company}'
                UNION SELECT 
                    "Payment Entry" AS `dt`,
                    `tabPayment Entry`.`name` AS `dn`
                FROM `tabPayment Entry`
                WHERE
                    `tabPayment Entry`.`posting_date` >= '{start_date}'
                    AND `tabPayment Entry`.`posting_date` <= '{end_date}'
                    AND `tabPayment Entry`.`docstatus` = 1
                    AND `tabPayment Entry`.`exported_to_abacus` = 0
                    AND `tabPayment Entry`.`company` = '{company}';""".format(
                    start_date=self.from_date, end_date=self.to_date, 
                    company=self.company)
        
        docs = frappe.db.sql(document_query, as_dict=True)
        
        # clear all children
        self.references = []
        
        # add to child table
        for doc in docs:
            row = self.append('references', {'dt': doc['dt'], 'dn': doc['dn']})
        self.save()
        
        # mark as exported
        sinvs = self.get_docs(docs, "Sales Invoice")
        pinvs = self.get_docs(docs, "Purchase Invoice")
        pes = self.get_docs(docs, "Payment Entry")
        update_query = """UPDATE `tabSales Invoice`
                SET `tabSales Invoice`.`exported_to_abacus` = 1
                WHERE
                    `tabSales Invoice`.`name` IN ({sinvs});""".format(
                    sinvs=self.get_sql_list(sinvs))
        frappe.db.sql(update_query)
        update_query = """UPDATE `tabPurchase Invoice`
                SET `tabPurchase Invoice`.`exported_to_abacus` = 1
                WHERE
                    `tabPurchase Invoice`.`name` IN ({pinvs});""".format(
                    pinvs=self.get_sql_list(pinvs))
        frappe.db.sql(update_query)
        update_query = """UPDATE `tabPayment Entry`
                SET `tabPayment Entry`.`exported_to_abacus` = 1
                WHERE
                    `tabPayment Entry`.`name` IN ({pes});""".format(
                    pes=self.get_sql_list(pes))
        frappe.db.sql(update_query)
        return
    
    # extract document names of one doctype as list
    def get_docs(self, references, dt):
        docs = []
        for d in references:
            if d['dt'] == dt:
                docs.append(d['dn'])
        return docs
    
    # safe call to get SQL IN statement    
    def get_sql_list(self, docs):
        if docs:
            return (','.join('"{0}"'.format(w) for w in docs))
        else:
            return '""'
    
    # reset export flags
    def reset_export_flags(self):
        sql_query = """UPDATE `tabGL Entry` SET `exported_to_abacus` = 0;"""
        frappe.db.sql(sql_query, as_dict=True)
        sql_query = """UPDATE `tabSales Invoice` SET `exported_to_abacus` = 0;"""
        frappe.db.sql(sql_query, as_dict=True)
        sql_query = """UPDATE `tabPayment Entry` SET `exported_to_abacus` = 0;"""
        frappe.db.sql(sql_query, as_dict=True)
        sql_query = """UPDATE `tabPurchase Invoice` SET `exported_to_abacus` = 0;"""
        frappe.db.sql(sql_query, as_dict=True)
        return { 'message': 'OK' }
    
    # get account number
    def get_account_number(self, account_name):
        if account_name:
            return frappe.get_value("Account", account_name, "account_number")
        else:
            return None
        
    # prepare transfer file
    def render_transfer_file(self):
        # collect task information
        if self.aggregated == 1:
            """ aggregated method """
            data = {
                'transactions': self.get_aggregated_transactions()
            }
                
        else:
            # normal method (each document)
            data = {
                'transactions': self.get_individual_transactions()
            }            
            
        
        content = frappe.render_template('erpnextswiss/erpnextswiss/doctype/abacus_export_file/transfer_file.html', data)
        return {'content': content}

    # get aggregated transactions 
    def get_aggregated_transactions(self):
        transactions = []
        sinvs = self.get_docs([ref.__dict__ for ref in self.references], "Sales Invoice")
        sql_query = """SELECT `tabSales Invoice`.`name`, 
                  `tabSales Invoice`.`posting_date`, 
                  `tabSales Invoice`.`currency`, 
                  SUM(`tabSales Invoice`.`base_grand_total`) AS `debit`, 
                  `tabSales Invoice`.`debit_to`,
                  SUM(`tabSales Invoice`.`base_net_total`) AS `income`, 
                  `tabSales Invoice Item`.`income_account`,  
                  SUM(`tabSales Invoice`.`total_taxes_and_charges`) AS `tax`, 
                  `tabSales Taxes and Charges`.`account_head`,
                  `tabSales Invoice`.`taxes_and_charges`,
                  `tabSales Taxes and Charges`.`rate`,
                  CONCAT(IFNULL(`tabSales Invoice`.`debit_to`, ""),
                    IFNULL(`tabSales Invoice Item`.`income_account`, ""),  
                    IFNULL(`tabSales Taxes and Charges`.`account_head`, "")
                  ) AS `key`
                FROM `tabSales Invoice`
                LEFT JOIN `tabSales Invoice Item` ON `tabSales Invoice`.`name` = `tabSales Invoice Item`.`parent`
                LEFT JOIN `tabSales Taxes and Charges` ON `tabSales Invoice`.`name` = `tabSales Taxes and Charges`.`parent`
                WHERE `tabSales Invoice`.`name` IN ({sinvs})
                GROUP BY `key`""".format(sinvs=self.get_sql_list(sinvs))
        sinv_items = frappe.db.sql(sql_query, as_dict=True)    
        for item in sinv_items:
            if item.taxes_and_charges:
                tax_record = frappe.get_doc("Sales Taxes and Charges Template", item.taxes_and_charges)
                tax_code = tax_record.tax_code
            else:
                tax_code = None
            # create content
            transactions.append({
                'account': self.get_account_number(item.debit_to), 
                'amount': item.debit, 
                'against_singles': [{
                    'account': self.get_account_number(item.income_account),
                    'amount': item.income,
                    'currency': item.currency
                }],
                'debit_credit': "D", 
                'date': self.to_date, 
                'currency': item.currency, 
                'tax_account': self.get_account_number(item.account_head) or None, 
                'tax_amount': item.tax or None, 
                'tax_rate': item.rate or None, 
                'tax_code': tax_code or "312", 
                'tax_currency': base_currency,
                'text1': item.name
            })
        
        pinvs = self.get_docs([ref.__dict__ for ref in self.references], "Purchase Invoice")
        sql_query = """SELECT `tabPurchase Invoice`.`name`, 
              `tabPurchase Invoice`.`posting_date`, 
              `tabPurchase Invoice`.`currency`, 
              SUM(`tabPurchase Invoice`.`base_grand_total`) AS `credit`, 
              `tabPurchase Invoice`.`credit_to`,
              SUM(`tabPurchase Invoice`.`base_net_total`) AS `expense`, 
              `tabPurchase Invoice Item`.`expense_account`,  
              SUM(`tabPurchase Invoice`.`base_total_taxes_and_charges`) AS `tax`, 
              `tabPurchase Taxes and Charges`.`account_head`,
              `tabPurchase Invoice`.`taxes_and_charges`,
              `tabPurchase Taxes and Charges`.`rate`,
              CONCAT(IFNULL(`tabPurchase Invoice`.`credit_to`, ""),
                IFNULL(`tabPurchase Invoice Item`.`expense_account`, ""),  
                IFNULL(`tabPurchase Taxes and Charges`.`account_head`, "")
              ) AS `key`
            FROM `tabPurchase Invoice`
            LEFT JOIN `tabPurchase Invoice Item` ON `tabPurchase Invoice`.`name` = `tabPurchase Invoice Item`.`parent`
            LEFT JOIN `tabPurchase Taxes and Charges` ON `tabPurchase Invoice`.`name` = `tabPurchase Taxes and Charges`.`parent`
            WHERE `tabPurchase Invoice`.`name` IN ({pinvs})
            GROUP BY `key`""".format(pinvs=self.get_sql_list(pinvs))
        
        pinv_items = frappe.db.sql(sql_query, as_dict=True)
        # create item entries
        for item in pinv_items:
            if item.taxes_and_charges:
                tax_record = frappe.get_doc("Purchase Taxes and Charges Template", item.taxes_and_charges)
                tax_code = tax_record.tax_code
            else:
                tax_code = None
            # create content
            transactions.append({
                'account': self.get_account_number(item.credit_to), 
                'amount': item.credit, 
                'against_singles': [{
                    'account': self.get_account_number(item.expense_account),
                    'amount': item.expense,
                    'currency': item.currency
                }],
                'debit_credit': "C", 
                'date': self.to_date, 
                'currency': item.currency, 
                'tax_account': self.get_account_number(item.account_head) or None, 
                'tax_amount': item.tax or None, 
                'tax_rate': item.rate or None, 
                'tax_currency': base_currency,
                'tax_code': tax_code or "312", 
                'text1': item.name
            })
            
        # add payment entry transactions
        pes = self.get_docs([ref.__dict__ for ref in self.references], "Payment Entry")
        sql_query = """SELECT `tabPayment Entry`.`name`,
                  `tabPayment Entry`.`posting_date`, 
                  `tabPayment Entry`.`paid_from_account_currency` AS `currency`,
                  SUM(`tabPayment Entry`.`paid_amount`) AS `amount`, 
                  `tabPayment Entry`.`paid_from`,
                  `tabPayment Entry`.`paid_to`,
                  CONCAT(IFNULL(`tabPayment Entry`.`paid_from`, ""),
                    IFNULL(`tabPayment Entry`.`paid_to`, "")
                  ) AS `key`
                FROM `tabPayment Entry`
                WHERE `tabPayment Entry`.`name` IN ({pes})
                GROUP BY `key`
            """.format(pes=self.get_sql_list(pes))

        pe_items = frappe.db.sql(sql_query, as_dict=True)
        
        # create item entries
        for item in pe_items:
            # create content
            transactions.append({
                'account': self.get_account_number(item.paid_from), 
                'amount': item.amount, 
                'against_singles': [{
                    'account': self.get_account_number(item.paid_to),
                    'amount': item.amount,
                    'currency': item.currency
                }],
                'debit_credit': "C", 
                'date': self.to_date, 
                'currency': item.currency, 
                'tax_account': None, 
                'tax_amount': None, 
                'tax_rate': None, 
                'tax_code': None, 
                'text1': item.name
            })
        
        return transactions


    def get_individual_transactions(self):
        base_currency = frappe.get_value("Company", self.company, "default_currency")
        transactions = []
        sinvs = self.get_docs([ref.__dict__ for ref in self.references], "Sales Invoice")
        sql_query = """SELECT DISTINCT `tabSales Invoice`.`name`, 
                  `tabSales Invoice`.`posting_date`, 
                  `tabSales Invoice`.`currency`, 
                  `tabSales Invoice`.`grand_total` AS `debit`, 
                  `tabSales Invoice`.`base_grand_total` AS `base_debit`,
                  `tabSales Invoice`.`debit_to`,
                  `tabSales Invoice`.`net_total` AS `income`, 
                  `tabSales Invoice`.`base_net_total` AS `base_income`, 
                  `tabSales Invoice Item`.`income_account`,  
                  `tabSales Invoice`.`base_total_taxes_and_charges` AS `tax`, 
                  `tabSales Taxes and Charges`.`account_head`,
                  `tabSales Invoice`.`taxes_and_charges`,
                  `tabSales Taxes and Charges`.`rate`,
                  `tabSales Invoice`.`customer_name`,
                  `tabSales Invoice`.`conversion_rate`
                FROM `tabSales Invoice`
                LEFT JOIN `tabSales Invoice Item` ON `tabSales Invoice`.`name` = `tabSales Invoice Item`.`parent`
                LEFT JOIN `tabSales Taxes and Charges` ON (`tabSales Invoice`.`name` = `tabSales Taxes and Charges`.`parent` AND  `tabSales Taxes and Charges`.`idx` = 1)
                WHERE `tabSales Invoice`.`name` IN ({sinvs});""".format(sinvs=self.get_sql_list(sinvs))
        sinv_items = frappe.db.sql(sql_query, as_dict=True)    
        for item in sinv_items:
            if item.taxes_and_charges:
                tax_record = frappe.get_doc("Sales Taxes and Charges Template", item.taxes_and_charges)
                tax_code = tax_record.tax_code
            else:
                tax_code = None
            # create content
            if item.customer_name:
                text2 = cgi.escape(item.customer_name)
            else:
                text2 = ""
            transactions.append({
                'account': self.get_account_number(item.debit_to), 
                'amount': item.debit, 
                'currency': item.currency, 
                'key_amount': item.base_debit, 
                'key_currency': base_currency,
                'exchange_rate': item.conversion_rate,
                'against_singles': [{
                    'account': self.get_account_number(item.income_account),
                    'amount': item.base_income,
                    'currency': base_currency
                }],
                'debit_credit': "D", 
                'date': item.posting_date, 
                'tax_account': self.get_account_number(item.account_head) or None, 
                'tax_amount': item.tax or None, 
                'tax_rate': item.rate or None, 
                'tax_currency': base_currency,
                'tax_code': tax_code or "312", 
                'text1': cgi.escape(item.name),
                'text2': text2
            })
        
        pinvs = self.get_docs([ref.__dict__ for ref in self.references], "Purchase Invoice")
        sql_query = """SELECT DISTINCT `tabPurchase Invoice`.`name`, 
                  `tabPurchase Invoice`.`posting_date`, 
                  `tabPurchase Invoice`.`currency`, 
                  `tabPurchase Invoice`.`grand_total` AS `credit`, 
                  `tabPurchase Invoice`.`base_grand_total` AS `base_credit`,
                  `tabPurchase Invoice`.`credit_to`,
                  `tabPurchase Invoice`.`net_total` AS `expense`,
                  `tabPurchase Invoice`.`base_net_total` AS `base_expense`, 
                  `tabPurchase Invoice Item`.`expense_account`,  
                  `tabPurchase Invoice`.`base_total_taxes_and_charges` AS `tax`, 
                  `tabPurchase Taxes and Charges`.`account_head`,
                  `tabPurchase Invoice`.`taxes_and_charges`,
                  `tabPurchase Taxes and Charges`.`rate`,
                  `tabPurchase Invoice`.`supplier_name`
                FROM `tabPurchase Invoice`
                LEFT JOIN `tabPurchase Invoice Item` ON `tabPurchase Invoice`.`name` = `tabPurchase Invoice Item`.`parent`
                LEFT JOIN `tabPurchase Taxes and Charges` ON (`tabPurchase Invoice`.`name` = `tabPurchase Taxes and Charges`.`parent` AND  `tabPurchase Taxes and Charges`.`idx` = 1)
                WHERE `tabPurchase Invoice`.`name` IN ({pinvs});""".format(pinvs=self.get_sql_list(pinvs))
        
        pinv_items = frappe.db.sql(sql_query, as_dict=True)
        # create item entries
        if item.supplier_name:
            text2 = cgi.escape(item.supplier_name)
        else:
            text2 = ""
        for item in pinv_items:
            if item.taxes_and_charges:
                tax_record = frappe.get_doc("Purchase Taxes and Charges Template", item.taxes_and_charges)
                tax_code = tax_record.tax_code
            else:
                tax_code = None
            # create content
            transactions.append({
                'account': self.get_account_number(item.credit_to), 
                'amount': item.credit, 
                'key_amount': item.base_credit, 
                'key_currency': base_currency,  
                'against_singles': [{
                    'account': self.get_account_number(item.expense_account),
                    'amount': item.base_expense,
                    'currency': item.currency
                }],
                'debit_credit': "C", 
                'date': item.posting_date, 
                'currency': item.currency, 
                'tax_account': self.get_account_number(item.account_head) or None, 
                'tax_amount': item.tax or None, 
                'tax_rate': item.rate or None, 
                'tax_code': tax_code or "312", 
                'tax_currency': base_currency,
                'text1': cgi.escape(item.name),
                'text2': text2
            })
            
        # add payment entry transactions
        pes = self.get_docs([ref.__dict__ for ref in self.references], "Payment Entry")
        sql_query = """SELECT `tabPayment Entry`.`name`,
                      `tabPayment Entry`.`posting_date`, 
                      `tabPayment Entry`.`paid_from_account_currency` AS `currency`,
                      `tabPayment Entry`.`paid_amount` AS `amount`, 
                      `tabPayment Entry`.`paid_from`,
                      `tabPayment Entry`.`paid_to`,
                      CONCAT(IFNULL(`tabPayment Entry`.`paid_from`, ""),
                        IFNULL(`tabPayment Entry`.`paid_to`, "")
                      ) AS `key`
                    FROM `tabPayment Entry`
                    WHERE`tabPayment Entry`.`name` IN ({pes})
            """.format(pes=self.get_sql_list(pes))

        pe_items = frappe.db.sql(sql_query, as_dict=True)
        
        # create item entries
        for item in pe_items:
            # create content
            transactions.append({
                'account': self.get_account_number(item.paid_from), 
                'amount': item.amount, 
                'against_singles': [{
                    'account': self.get_account_number(item.paid_to),
                    'amount': item.amount,
                    'currency': item.currency
                }],
                'debit_credit': "C", 
                'date': item.posting_date, 
                'currency': item.currency, 
                'tax_account': None, 
                'tax_amount': None, 
                'tax_rate': None, 
                'tax_code': None, 
                'text1': cgi.escape(item.name)
            })
        
        return transactions        
        
