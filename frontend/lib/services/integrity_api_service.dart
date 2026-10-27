import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/integrity_models.dart';

class IntegrityApiService {
  static const String baseUrl = 'http://127.0.0.1:8000/v1/integrity';
  static const Map<String, String> caregiverHeaders = {
    'Content-Type': 'application/json',
    'X-Demo-Role': 'demo-caregiver-2024',
  };

  /// Query the Memory Integrity Firewall
  static Future<IntegrityAskResult> askFirewall(String question, {int patientId = 1}) async {
    final response = await http.post(
      Uri.parse('$baseUrl/ask'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'question': question,
        'patient_id': patientId,
        'lang': 'en',
      }),
    );
    if (response.statusCode == 200) {
      return IntegrityAskResult.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to evaluate memory integrity: ${response.statusCode}');
  }

  /// Fetch all memory claims with provenance
  static Future<List<MemoryClaimModel>> getClaims({int patientId = 1}) async {
    final response = await http.get(Uri.parse('$baseUrl/claims?patient_id=$patientId'));
    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data.map((e) => MemoryClaimModel.fromJson(e)).toList();
    }
    throw Exception('Failed to load memory claims');
  }

  /// Fetch open caregiver disagreements
  static Future<List<MemoryConflictModel>> getConflicts({int patientId = 1}) async {
    final response = await http.get(Uri.parse('$baseUrl/conflicts?patient_id=$patientId&resolution_status=open'));
    if (response.statusCode == 200) {
      final List data = jsonDecode(response.body);
      return data.map((e) => MemoryConflictModel.fromJson(e)).toList();
    }
    throw Exception('Failed to load conflicts');
  }

  /// Resolve a caregiver disagreement
  static Future<bool> resolveConflict(int conflictId, int winningClaimId, String actor) async {
    final response = await http.post(
      Uri.parse('$baseUrl/conflicts/$conflictId/resolve'),
      headers: caregiverHeaders,
      body: jsonEncode({
        'winning_claim_id': winningClaimId,
        'actor': actor,
        'note': 'Resolved via Flutter CardioLife interface.',
      }),
    );
    return response.statusCode == 200;
  }
}
