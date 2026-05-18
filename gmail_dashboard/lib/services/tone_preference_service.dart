import 'package:shared_preferences/shared_preferences.dart';

// Persists the last tone used per sender email address.
// Key format: "tone_pref:<sender>" → tone string (e.g. "friendly")
//
// WHY CLIENT-SIDE?
//   Tone preference is a UI hint, not business data. It doesn't need
//   to survive server changes or sync across devices. SharedPreferences
//   is the right layer — zero network cost, instant reads.
class TonePreferenceService {
  static const _prefix = 'tone_pref:';
  static const _defaultTone = 'professional';

  // Normalize the sender key so "Alice <alice@co.com>" and "alice@co.com"
  // both map to the same preference entry.
  static String _key(String sender) {
    final email = _extractEmail(sender);
    return '$_prefix$email';
  }

  static String _extractEmail(String sender) {
    final match = RegExp(r'<(.+?)>').firstMatch(sender);
    return (match?.group(1) ?? sender).trim().toLowerCase();
  }

  Future<String> load(String sender) async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_key(sender)) ?? _defaultTone;
  }

  Future<void> save(String sender, String tone) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key(sender), tone);
  }
}
