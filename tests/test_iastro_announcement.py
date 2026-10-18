import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location("announce",Path(__file__).parents[1]/"scripts/announce-iastro-w42.py")
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class AnnouncementTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.record=Path(self.tmp.name)/"receipt.json"
  self.calls=[]
  self.saved=[]
 def api(self,method,payload):
  self.calls.append((method,payload))
  if method=="getMe": return {"id":123}
  if method=="getChat": return {"id":-1001,"type":"channel","username":"VeilleIA_HL","title":"Le Radar iA · iAstro"}
  if method=="getChatMember": return {"can_post_messages":True}
  if method=="sendPhoto": return {"message_id":77,"chat":{"id":-1001}}
  raise AssertionError(method)
 def save(self,record):
  self.saved.append(record["status"])
  self.record.write_text(json.dumps(record))
 def run_main(self,send=False,api=None,history="no announcement"):
  with patch.object(a,"RECEIPT",self.record),patch.object(a,"tg",api or self.api),patch.object(a,"persist",self.save),patch.object(a,"history_check",return_value=(history,["VeilleIA_HL/325"])),patch.object(a,"verify_live",return_value="sha"),patch.dict(a.os.environ,{"TELEGRAM_CHANNEL_ID":"-1001"}),patch("sys.argv",["announce"]+(["--send"] if send else [])):
   a.main()
 def test_dry_run_has_no_send_or_reservation(self):
  self.run_main()
  self.assertNotIn("sendPhoto",[x[0] for x in self.calls]);self.assertEqual(self.saved,[])
 def test_success_reserved_before_send_and_repeat_is_noop(self):
  def api(method,payload):
   if method=="sendPhoto": self.assertEqual(self.saved,["reserved"])
   return self.api(method,payload)
  self.run_main(True,api)
  self.assertEqual(self.saved,["reserved","sent"])
  payload=next(p for m,p in self.calls if m=="sendPhoto")
  self.assertFalse(payload["disable_notification"])
  self.assertEqual(payload["caption"],a.CAPTION)
  self.run_main(True)
  self.assertEqual(sum(m=="sendPhoto" for m,p in self.calls),1)
 def test_reserved_blocks_retry(self):
  self.record.write_text('{"status":"reserved"}')
  with self.assertRaises(RuntimeError): self.run_main(True)
  self.assertEqual(self.calls,[])
 def test_public_duplicate_does_not_send(self):
  self.run_main(True,history=a.PAGE)
  self.assertNotIn("sendPhoto",[x[0] for x in self.calls]);self.assertEqual(self.saved,[])
 def test_wrong_channel_fails_closed(self):
  def api(m,p):
   result=self.api(m,p)
   if m=="getChat":result["username"]="OtherChannel"
   return result
  with self.assertRaises(RuntimeError): self.run_main(True,api)
  self.assertEqual(self.saved,[])
 def test_ambiguous_send_is_not_retried(self):
  def api(m,p):
   if m=="sendPhoto":
    self.calls.append((m,p));raise RuntimeError("uncertain")
   return self.api(m,p)
  with self.assertRaises(RuntimeError): self.run_main(True,api)
  with self.assertRaises(RuntimeError): self.run_main(True,api)
  self.assertEqual(sum(m=="sendPhoto" for m,p in self.calls),1)
  self.assertTrue(json.loads(self.record.read_text())["verification_required"])
if __name__=="__main__":unittest.main()

