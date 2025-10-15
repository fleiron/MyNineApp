import SwiftUI

struct HomeView: View {
    // MARK: - State
    @State private var turns: [ChatTurn] = []              // конструктор диалога
    @State private var draftText: String = ""
    @State private var draftRole: ChatRole = .partner

    @State private var relationship: Relationship = .girlfriend
    @State private var scenario: Scenario = .defuse_tension
    @State private var tone: Tone = .friendly

    @State private var targetGender: String? = nil
    @State private var personalness: Double = 55
    @State private var intensify: String? = nil

    @State private var isLoading = false
    @State private var response: GenerateResponse?
    @State private var error: String?

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color.black, Color(red:0.05, green:0.07, blue:0.12)],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 18) {

                    // Title
                    VStack(spacing: 6) {
                        Text("TextSense — AI Messenger Assistant")
                            .font(.custom("Rubik-Bold", size: 24))
                        Text("Собери контекст диалога и получи 3 готовых ответа")
                            .font(.custom("Rubik-Regular", size: 13))
                            .opacity(0.7)
                    }
                    .multilineTextAlignment(.center)

                    // MARK: Chat Builder
                    chatBuilderSection

                    // MARK: Quick Paste
                    pasteHelper

                    // MARK: Controls (compact)
                    controlsSection

                    // MARK: Generate
                    generateButton

                    // MARK: Error
                    if let error {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }

                    // MARK: Results
                    resultsSection

                    Spacer(minLength: 32)
                }
                .padding(16)
                .foregroundStyle(.white)
            }
        }
    }

    // MARK: - Sections

    private var chatBuilderSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Context")
                .font(.custom("Rubik-Bold", size: 18))

            // Display last turns as bubbles
            if turns.isEmpty {
                Text("Добавь 2–5 реплик (кто что написал).")
                    .font(.custom("Rubik-Regular", size: 13))
                    .opacity(0.7)
            } else {
                VStack(spacing: 8) {
                    ForEach(Array(turns.enumerated()), id: \.offset) { idx, t in
                        bubble(turn: t, index: idx)
                    }
                }
            }

            // Composer
            HStack(spacing: 8) {
                Picker("", selection: $draftRole) {
                    Text("Partner").tag(ChatRole.partner)
                    Text("You").tag(ChatRole.user)
                    Text("Other").tag(ChatRole.other)
                }
                .pickerStyle(.segmented)
                .frame(width: 220)

                TextField("Введите реплику…", text: $draftText, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .font(.custom("Rubik-Regular", size: 15))
                    .lineLimit(1...3)

                Button {
                    addTurn()
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.title2)
                }
                .disabled(draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(10)
            .background(Color.white.opacity(0.06))
            .cornerRadius(14)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(.white.opacity(0.08)))
        }
    }

    private func bubble(turn: ChatTurn, index: Int) -> some View {
        HStack(alignment: .top) {
            if turn.role == "user" { Spacer(minLength: 24) }
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Text(turn.role == "user" ? "You" : (turn.role == "partner" ? "Partner" : "Other"))
                        .font(.custom("Rubik-Bold", size: 12))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(turn.role == "user" ? Color.blue.opacity(0.2) : Color.orange.opacity(0.2))
                        .clipShape(Capsule())
                    Text("#\(index+1)")
                        .font(.caption2)
                        .opacity(0.6)
                }
                Text(turn.text)
                    .font(.custom("Rubik-Regular", size: 16))
                    .fixedSize(horizontal: false, vertical: true)

                HStack(spacing: 10) {
                    Button(role: .destructive) {
                        withAnimation {
                            _ = turns.remove(at: index)
                        }

                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                    .buttonStyle(.bordered)

                    if index > 0 {
                        Button {
                            withAnimation {
                                let item = turns.remove(at: index)
                                turns.insert(item, at: index-1)
                            }
                        } label: {
                            Label("Up", systemImage: "arrow.up")
                        }
                        .buttonStyle(.bordered)
                    }
                    if index < turns.count - 1 {
                        Button {
                            withAnimation {
                                let item = turns.remove(at: index)
                                turns.insert(item, at: index+1)
                            }
                        } label: {
                            Label("Down", systemImage: "arrow.down")
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .font(.caption)
            }
            .padding(12)
            .background {
                (turn.role == "user" ? Color.blue : Color.orange)
                    .opacity(0.2)
            }
            .cornerRadius(14)
           

            if turn.role != "user" { Spacer(minLength: 24) }
        }
    }
    
    

    private var pasteHelper: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Быстрый ввод")
                    .font(.custom("Rubik-Bold", size: 16))
                Spacer()
                Button {
                    if let text = UIPasteboard.general.string {
                        let parsed = parseDialog(text)
                        withAnimation { self.turns = parsed }
                    }
                } label: {
                    Label("Paste from clipboard", systemImage: "doc.on.clipboard")
                }
                .buttonStyle(.bordered)
            }
            Text("Поддерживается формат:\nYou: ...\nPartner: ...\n(строка за строкой). Необозначенные строки чередуются Partner/You.")
                .font(.custom("Rubik-Regular", size: 12))
                .opacity(0.6)
        }
    }

    private var controlsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Settings")
                .font(.custom("Rubik-Bold", size: 18))

            HStack {
                VStack(alignment: .leading) {
                    Text("Relationship").font(.caption).opacity(0.7)
                    Picker("", selection: $relationship) {
                        ForEach(Relationship.allCases) { r in Text(r.rawValue).tag(r) }
                    }.pickerStyle(.menu)
                }
                Spacer()
                VStack(alignment: .leading) {
                    Text("Scenario").font(.caption).opacity(0.7)
                    Picker("", selection: $scenario) {
                        ForEach(Scenario.allCases) { s in Text(s.rawValue).tag(s) }
                    }.pickerStyle(.menu)
                }
                Spacer()
                VStack(alignment: .leading) {
                    Text("Tone").font(.caption).opacity(0.7)
                    Picker("", selection: $tone) {
                        ForEach(Tone.allCases) { t in Text(t.rawValue).tag(t) }
                    }.pickerStyle(.menu)
                }
            }

            HStack {
                VStack(alignment: .leading) {
                    Text("Target gender").font(.caption).opacity(0.7)
                    Picker("", selection: Binding(
                        get: { targetGender ?? "none" },
                        set: { targetGender = $0 == "none" ? nil : $0 }
                    )) {
                        Text("none").tag("none")
                        Text("female").tag("female")
                        Text("male").tag("male")
                        Text("other").tag("other")
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: 180)
                }

                Spacer()

                VStack(alignment: .leading) {
                    Text("Personalness").font(.caption).opacity(0.7)
                    HStack {
                        Slider(value: $personalness, in: 0...100, step: 1)
                        Text("\(Int(personalness))")
                            .frame(width: 36)
                    }
                }
            }

            HStack {
                Button("Make softer") { intensify = "softer"; Task { await generate() } }
                    .buttonStyle(.bordered)
                Button("Make edgier") { intensify = "edgier"; Task { await generate() } }
                    .buttonStyle(.bordered)
            }
        }
        .padding(12)
        .background(Color.white.opacity(0.06))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(.white.opacity(0.08)))
    }

    private var generateButton: some View {
        Button {
            intensify = nil
            Task { await generate() }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                Text(isLoading ? "Generating..." : "Generate replies")
                    .font(.custom("Rubik-Bold", size: 18))
            }
        }
        .buttonStyle(.borderedProminent)
        .disabled(isLoading || turns.isEmpty)
    }

    private var resultsSection: some View {
        Group {
            if let resp = response {
                Text("Detected language: \(resp.language ?? "auto")")
                    .font(.custom("Rubik-Regular", size: 12))
                    .opacity(0.7)

                VStack(spacing: 12) {
                    ForEach(resp.options) { opt in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(opt.label)
                                .font(.custom("Rubik-Bold", size: 14))
                                .opacity(0.8)
                            Text(opt.text)
                                .font(.custom("Rubik-Regular", size: 18))
                                .fixedSize(horizontal: false, vertical: true)
                            HStack {
                                Button {
                                    UIPasteboard.general.string = opt.text
                                    Task { await APIService.shared.feedback(generationId: resp.id, chosen: opt) }
                                } label: {
                                    Label("Copy", systemImage: "doc.on.doc")
                                }
                                .buttonStyle(.bordered)

                                Button {
                                    Task { await APIService.shared.feedback(generationId: resp.id, chosen: opt) }
                                } label: {
                                    Label("Use", systemImage: "checkmark.circle.fill")
                                }
                                .buttonStyle(.borderedProminent)
                            }
                        }
                        .padding()
                        .background(Color.white.opacity(0.06))
                        .cornerRadius(16)
                    }
                }
            }
        }
    }

    // MARK: - Actions

    private func addTurn() {
        let trimmed = draftText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let role: String = {
            switch draftRole {
            case .user: return "user"
            case .partner: return "partner"
            case .other: return "other"
            }
        }()

        withAnimation {
            turns.append(ChatTurn(role: role, text: trimmed))
            draftText = ""
            draftRole = .partner
        }
    }

    private func parseDialog(_ raw: String) -> [ChatTurn] {
        let lines = raw
            .split(separator: "\n")
            .map { String($0) }
            .filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }

        var out: [ChatTurn] = []
        for (idx, line) in lines.enumerated() {
            let lower = line.lowercased()
            if lower.hasPrefix("you:") {
                let txt = String(line.dropFirst(4)).trimmingCharacters(in: .whitespaces)
                out.append(ChatTurn(role: "user", text: txt))
            } else if lower.hasPrefix("partner:") {
                let txt = String(line.dropFirst(8)).trimmingCharacters(in: .whitespaces)
                out.append(ChatTurn(role: "partner", text: txt))
            } else {
                // alternate if no prefix
                out.append(ChatTurn(role: idx % 2 == 0 ? "partner" : "user", text: line))
            }
        }
        return out
    }

    private func generate() async {
        isLoading = true; error = nil; response = nil
        let req = GenerateRequest(
            messages: turns,
            relationship: relationship,
            scenario: scenario,
            tone: tone,
            language: nil, // автоопределение на бэке
            target_gender: targetGender,
            personalness: Int(personalness),
            intensify: intensify
        )
        do {
            let resp = try await APIService.shared.generate(req: req)
            withAnimation { self.response = resp }
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Helpers (local types used в UI)

enum ChatRole: String, CaseIterable, Identifiable {
    case user, partner, other
    var id: String { rawValue }
}

