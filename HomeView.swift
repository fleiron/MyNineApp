import SwiftUI

struct HomeView: View {
    @State private var rawDialog: String = ""
    @State private var relationship: Relationship = .girlfriend
    @State private var scenario: Scenario = .defuse_tension
    @State private var tone: Tone = .friendly
    @State private var language: String? = nil  // auto
    @State private var targetGender: String? = nil
    @State private var personalness: Double = 55
    @State private var intensify: String? = nil
    @State private var isLoading = false
    @State private var response: GenerateResponse?
    @State private var error: String?

    var body: some View {
        ZStack {
            LinearGradient(colors: [Color.black, Color(red:0.05, green:0.07, blue:0.12)], startPoint: .topLeading, endPoint: .bottomTrailing)
                .ignoresSafeArea()

            ScrollView {
                VStack(spacing: 16) {
                    Text("TextSense — AI Messenger Assistant")
                        .font(.custom("Rubik-Bold", size: 24))
                        .multilineTextAlignment(.center)

                    Group {
                        Text("Paste last 2–5 turns from your chat (both sides).")
                            .font(.custom("Rubik-Regular", size: 14))
                            .opacity(0.8)
                        TextEditor(text: $rawDialog)
                            .frame(minHeight: 140)
                            .padding()
                            .background(Color.white.opacity(0.06))
                            .cornerRadius(16)
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.08)))
                            .font(.custom("Rubik-Regular", size: 16))
                    }

                    Group {
                        Picker("Relationship", selection: $relationship) {
                            ForEach(Relationship.allCases) { r in Text(r.rawValue).tag(r) }
                        }
                        .pickerStyle(.menu)

                        Picker("Scenario", selection: $scenario) {
                            ForEach(Scenario.allCases) { s in Text(s.rawValue).tag(s) }
                        }
                        .pickerStyle(.menu)

                        Picker("Tone", selection: $tone) {
                            ForEach(Tone.allCases) { t in Text(t.rawValue).tag(t) }
                        }
                        .pickerStyle(.menu)

                        HStack {
                            Text("Target gender")
                            Spacer()
                            Picker("", selection: Binding(
                                get: { targetGender ?? "none" },
                                set: { targetGender = $0 == "none" ? nil : $0 }
                            )) {
                                Text("none").tag("none")
                                Text("female").tag("female")
                                Text("male").tag("male")
                                Text("other").tag("other")
                            }.pickerStyle(.menu)
                        }

                        HStack {
                            Text("Personalness")
                            Slider(value: $personalness, in: 0...100, step: 1)
                            Text("\(Int(personalness))")
                                .frame(width: 36)
                        }

                        HStack {
                            Button("Make softer") { intensify = "softer"; Task { await generate() } }
                                .buttonStyle(.bordered)
                            Button("Make edgier") { intensify = "edgier"; Task { await generate() } }
                                .buttonStyle(.bordered)
                        }
                    }

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
                    .disabled(isLoading || rawDialog.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

                    if let error {
                        Text(error).foregroundStyle(.red).font(.footnote)
                    }

                    if let resp = response {
                        Text("Detected language: \(resp.language ?? "auto")")
                            .font(.custom("Rubik-Regular", size: 12))
                            .opacity(0.7)

                        ForEach(resp.options) { opt in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(opt.label)
                                    .font(.custom("Rubik-Bold", size: 14))
                                    .opacity(0.8)
                                Text(opt.text)
                                    .font(.custom("Rubik-Regular", size: 18))
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

                    Spacer(minLength: 40)
                }
                .padding(16)
                .foregroundStyle(.white)
            }
        }
    }

    private func parseDialog(_ raw: String) -> [ChatTurn] {
        // Simple heuristic: lines prefixed by "You:" or "Partner:"; otherwise infer alternating
        let lines = raw.split(separator: "\n").map { String($0) }.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        var turns: [ChatTurn] = []
        for (idx, line) in lines.enumerated() {
            if line.lowercased().hasPrefix("you:") {
                turns.append(.init(role: "user", text: String(line.dropFirst(4)).trimmingCharacters(in: .whitespaces)))
            } else if line.lowercased().hasPrefix("partner:") {
                turns.append(.init(role: "partner", text: String(line.dropFirst(8)).trimmingCharacters(in: .whitespaces)))
            } else {
                // alternate
                turns.append(.init(role: idx % 2 == 0 ? "partner" : "user", text: line))
            }
        }
        return turns
    }

    private func generate() async {
        isLoading = true; error = nil; response = nil
        let msgs = parseDialog(rawDialog)
        let req = GenerateRequest(
            messages: msgs,
            relationship: relationship,
            scenario: scenario,
            tone: tone,
            language: nil, // auto
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
