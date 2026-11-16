export interface Envelope<T> { code: number; message: string; data: T; request_id: string }
export interface User { id: string; username: string; role: 'student' | 'teacher' }
export interface LoginResult { access_token: string; token_type: 'bearer'; user: User }
export interface Course { id: string; name: string; description: string }
export interface Question {
  id: string; stem: string; options: { id: string; text: string }[]
  knowledge_point_ids: string[]; kind: 'single'
}
export interface Answer { question_id: string; selected_option_ids: string[] }
export type KnowledgeStatus = 'insufficient_evidence' | 'weak' | 'needs_practice' | 'mastered'
export interface KnowledgePointResult {
  knowledge_point_id: string; name: string; correct_count: number; sample_count: number
  accuracy: number | null; status: KnowledgeStatus
}
export interface Evidence {
  evidence_id: string; document_id: string; resource_id: string; chunk_id: string
  knowledge_point_ids: string[]; text: string; score: number
  location: string; source: string; title: string
}
export interface Report {
  attempt_id: string; mode: 'rule_template_demo'; knowledge_points: KnowledgePointResult[]
  evidence: Evidence[]
  recommendations: { knowledge_point_id: string; resource_id: string; title: string; reason: string }[]
  explanation: string
  comparison: { knowledge_point_id: string; before_accuracy: number | null; after_accuracy: number | null; delta: number | null }[]
  trace: { agent: string; status: string }[]; fallback_status: string | null
}
export interface Attempt {
  id: string; course_id: string; score: number; max_score: number; percentage: number
  created_at: number; baseline_attempt_id: string | null
  status: 'completed'; report: Report | null
  ai_status: 'completed' | 'unavailable' | 'disabled' | 'processing'; ai_message: string | null
}
export interface SubmitAttempt { course_id: string; answers: Answer[]; baseline_attempt_id?: string }
export interface TeacherOverview { user_count: number; question_count: number; attempt_count: number; resource_count: number }
