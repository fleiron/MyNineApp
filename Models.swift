import Foundation

struct ChatTurn: Codable, Identifiable {
    let id = UUID()
    var role: String // "user" | "partner" | "other"
    var text: String
}

enum Relationship: String, CaseIterable, Identifiable, Codable {
    case girlfriend, boyfriend, friend, coworker, boss, stranger, family, other
    var id: String { rawValue }
}

enum Scenario: String, CaseIterable, Identifiable, Codable {
    case defuse_tension, apologize, flirt, ask_out, schedule, negotiate, follow_up, reject_politely, say_no, clarify, congratulate, thank, other
    var id: String { rawValue }
}

enum Tone: String, CaseIterable, Identifiable, Codable {
    case confident, friendly, neutral, apologetic, playful, flirty, formal, direct, other
    var id: String { rawValue }
}

struct GenerateRequest: Codable {
    var messages: [ChatTurn]
    var relationship: Relationship
    var scenario: Scenario
    var tone: Tone
    var language: String? // nil => auto
    var target_gender: String? // "male"|"female"|"other"
    var personalness: Int
    var intensify: String? // "softer" | "edgier" | nil
}

struct ReplyOption: Codable, Identifiable {
    var id: String { label + text }
    let label: String
    let text: String
}

struct GenerateResponse: Codable {
    let id: String
    let language: String?
    let options: [ReplyOption]
}
