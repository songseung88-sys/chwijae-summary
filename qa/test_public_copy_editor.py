"""Public-site copy catalog/editability regression, without connecting to Firestore."""
import ast
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
API=ROOT/"api"
CATALOG=json.loads((API/"static/ui-copy-fields.json").read_text())
MAIN=(API/"main.py").read_text()
TREE=ast.parse(MAIN)
DEFAULTS=ast.literal_eval(next(n.value for n in TREE.body if isinstance(n,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=="DEFAULT_SITE_CONFIG" for t in n.targets)))

class PublicCopyTests(unittest.TestCase):
    def test_catalog_and_legacy_editor_migration(self):
        fields={item["key"]:item for item in CATALOG}
        self.assertEqual(len(fields),len(CATALOG))
        self.assertGreaterEqual(len(fields),65)
        for key in ("dashboard_title","hero_description","about_link",
                    "feedback_label","feedback_submit","annual_chart_title",
                    "publisher_chart_title","category_dialog_title",
                    "card_today_label","topic_primary_caption"):
            self.assertIn(key,fields)
        self.assertEqual(fields["feedback_label"]["default"],"의견이나 제안을 남겨주세요.")
        self.assertTrue(set(DEFAULTS).intersection(fields))
        self.assertIn('config["ui_copy"] = copy',MAIN)
        self.assertIn('config[key] = copy[key]',MAIN)

    def test_backend_is_password_protected_and_accepts_empty(self):
        self.assertIn('@app.put("/api/admin/ui-copy")',MAIN)
        endpoint=MAIN[MAIN.index('def update_public_ui_copy('):]
        self.assertIn("require_admin(x_admin_password)",endpoint)
        self.assertIn("isinstance(value, str)",endpoint)
        self.assertIn("ref.set",endpoint)
        self.assertNotIn("value.strip():",endpoint[:endpoint.index('return {"ok"')])

    def test_dashboard_and_about_use_all_fixed_text_layers(self):
        dashboard=(API/"static/index.html").read_text()
        app=(API/"static/app.js").read_text()
        about=(API/"static/about.html").read_text()
        about_js=(API/"static/about.js").read_text()
        feedback=(API/"static/feedback.js").read_text()
        for token in ("dashboardTitle","aboutLinkLabel","dateLabel","categoryCriteria"):
            self.assertIn('id="'+token+'"',dashboard)
        for text_key in ("collection_unknown","collection_done","dashboard_title",
                         "empty_articles","category_dialog_title","card_publisher_asof"):
            self.assertIn(text_key,app)
        self.assertIn("uiCopy(",app)
        self.assertIn("ui_copy",about_js)
        self.assertIn('id="feedbackPromptLabel">의견이나 제안을 남겨주세요.',about)
        self.assertNotIn("서비스에 대한 의견",about)
        self.assertIn("feedbackCopy(",feedback)
        self.assertIn('src="/static/feedback.js?v=2"',about)

    def test_admin_can_search_clear_reset_and_preview_selected_prose(self):
        admin=(API/"static/admin.html").read_text()
        js=(API/"static/admin.js").read_text()
        layout=(API/"static/about-layout-editor.js").read_text()
        for token in ("copyFilter","copyReload","configForm","saveButton"):
            self.assertIn('id="'+token+'"',admin)
        self.assertIn('/api/admin/ui-copy',js)
        self.assertIn('clear.textContent="문구 삭제"',js)
        self.assertIn('restore.textContent="기본값"',js)
        self.assertIn('data-format="큰글씨"',layout)
        self.assertIn('data-format="작은글씨"',layout)
        self.assertIn('data-format="굵게"',layout)
        self.assertIn("renderAboutText(preview",layout)

if __name__=="__main__":unittest.main()
