class MemoryClaimModel {
  final int id;
  final int patientId;
  final String statement;
  final String category;
  final String? subject;
  final String? propertyKey;
  final String? propertyValue;
  final String sourceType;
  final String? sourceDescription;
  final String? author;
  final String integrityStatus; // verified, unverified, needs_review, conflicting, expired, rejected
  final String? verifiedBy;
  final DateTime? verifiedAt;
  final DateTime? reviewDueDate;
  final DateTime? expiryDate;
  final int? supersedesId;
  final DateTime recordedAt;

  MemoryClaimModel({
    required this.id,
    required this.patientId,
    required this.statement,
    required this.category,
    this.subject,
    this.propertyKey,
    this.propertyValue,
    required this.sourceType,
    this.sourceDescription,
    this.author,
    required this.integrityStatus,
    this.verifiedBy,
    this.verifiedAt,
    this.reviewDueDate,
    this.expiryDate,
    this.supersedesId,
    required this.recordedAt,
  });

  factory MemoryClaimModel.fromJson(Map<String, dynamic> json) {
    return MemoryClaimModel(
      id: json['id'] as int,
      patientId: json['patient_id'] as int,
      statement: json['statement'] as String,
      category: json['category'] as String? ?? 'general',
      subject: json['subject'] as String?,
      propertyKey: json['property_key'] as String?,
      propertyValue: json['property_value'] as String?,
      sourceType: json['source_type'] as String? ?? 'caregiver_input',
      sourceDescription: json['source_description'] as String?,
      author: json['author'] as String?,
      integrityStatus: json['integrity_status'] as String? ?? 'unverified',
      verifiedBy: json['verified_by'] as String?,
      verifiedAt: json['verified_at'] != null ? DateTime.parse(json['verified_at']) : null,
      reviewDueDate: json['review_due_date'] != null ? DateTime.parse(json['review_due_date']) : null,
      expiryDate: json['expiry_date'] != null ? DateTime.parse(json['expiry_date']) : null,
      supersedesId: json['supersedes_id'] as int?,
      recordedAt: DateTime.parse(json['recorded_at']),
    );
  }
}

class MemoryConflictModel {
  final int id;
  final int patientId;
  final String subject;
  final String propertyKey;
  final int claimAId;
  final int claimBId;
  final String claimAStatement;
  final String claimBStatement;
  final String? claimAAuthor;
  final String? claimBAuthor;
  final String resolutionStatus;
  final int? winningClaimId;
  final DateTime detectedAt;

  MemoryConflictModel({
    required this.id,
    required this.patientId,
    required this.subject,
    required this.propertyKey,
    required this.claimAId,
    required this.claimBId,
    required this.claimAStatement,
    required this.claimBStatement,
    this.claimAAuthor,
    this.claimBAuthor,
    required this.resolutionStatus,
    this.winningClaimId,
    required this.detectedAt,
  });

  factory MemoryConflictModel.fromJson(Map<String, dynamic> json) {
    return MemoryConflictModel(
      id: json['id'] as int,
      patientId: json['patient_id'] as int,
      subject: json['subject'] as String,
      propertyKey: json['property_key'] as String,
      claimAId: json['claim_a_id'] as int,
      claimBId: json['claim_b_id'] as int,
      claimAStatement: json['claim_a_statement'] as String,
      claimBStatement: json['claim_b_statement'] as String,
      claimAAuthor: json['claim_a_author'] as String?,
      claimBAuthor: json['claim_b_author'] as String?,
      resolutionStatus: json['resolution_status'] as String? ?? 'open',
      winningClaimId: json['winning_claim_id'] as int?,
      detectedAt: DateTime.parse(json['detected_at']),
    );
  }
}

class IntegrityAskResult {
  final String decision; // ANSWER, WARN, REVIEW_REQUIRED, CONFLICT, ABSTAIN
  final String? answer;
  final List<MemoryClaimModel> supportingClaims;
  final List<MemoryClaimModel> conflictingClaims;
  final String? warning;
  final List<String> reasonCodes;

  IntegrityAskResult({
    required this.decision,
    this.answer,
    required this.supportingClaims,
    required this.conflictingClaims,
    this.warning,
    required this.reasonCodes,
  });

  factory IntegrityAskResult.fromJson(Map<String, dynamic> json) {
    return IntegrityAskResult(
      decision: (json['decision'] ?? json['decision_status']) as String,
      answer: json['answer'] as String?,
      supportingClaims: (json['supporting_claims'] as List<dynamic>? ?? [])
          .map((e) => MemoryClaimModel.fromJson(e as Map<String, dynamic>))
          .toList(),
      conflictingClaims: (json['conflicting_claims'] as List<dynamic>? ?? [])
          .map((e) => MemoryClaimModel.fromJson(e as Map<String, dynamic>))
          .toList(),
      warning: json['warning'] as String?,
      reasonCodes: (json['reason_codes'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
    );
  }
}
