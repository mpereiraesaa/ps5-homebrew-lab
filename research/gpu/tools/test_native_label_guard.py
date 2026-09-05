import unittest
from native_label_guard import classify

class TestGuard(unittest.TestCase):
 def test_complete(self):
  log="GPU ownership complete fence=0 target=0\nprobe_complete=true\nbatch_unmap_processed=0x00000001\n"+"\n".join(f"{x}=0x00000000" for x in ("agc_init","submit_dcb","batch_unmap","direct_release","virtual_release","agc_unload"))
  self.assertEqual(classify(log)["state"],"gpu_complete");self.assertTrue(classify(log)["close_allowed"])
 def test_incomplete_batch_cleanup_retains(self):
  log="GPU ownership complete fence=0 target=0\nprobe_complete=true\n"+"\n".join(f"{x}=0x00000000" for x in ("agc_init","submit_dcb","batch_unmap","direct_release","virtual_release","agc_unload"))
  self.assertEqual(classify(log)["state"],"unknown_retain")
 def test_timeout_retains(self):
  d=classify("submit_dcb=0x00000000\nPARKED_NATIVE_LABEL reason=ownership fence timeout; DO_NOT_CLOSE_PPSA99998\n")
  self.assertEqual(d["state"],"parked_retain");self.assertFalse(d["close_allowed"])
 def test_truncated_retains(self): self.assertFalse(classify("submit_dcb=0x00000000\n")["close_allowed"])
 def test_pre_submit_clean(self): self.assertTrue(classify("pre-submit clean failure; parked-safe; close exact title PPSA99998\n")["close_allowed"])

if __name__=="__main__": unittest.main()
