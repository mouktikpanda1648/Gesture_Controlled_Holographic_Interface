#include <Arduino.h>
#include <string.h>
// Configuration
constexpr const char* FW_VERSION = "1.0";
constexpr uint8_t LED_PIN = 18;
constexpr bool LED_ACTIVE_HIGH = true;
constexpr uint32_t SERIAL_BAUD_RATE = 115200;
constexpr size_t BUFFER_SIZE = 32;
constexpr uint32_t COMMAND_TIMEOUT_MS = 1000;
constexpr uint32_t FAILSAFE_TIMEOUT_MS = 5000;

// Internal State
class SystemState{
public:
    char commandBuffer[BUFFER_SIZE] = {};
    size_t commandLength = 0;
    bool discardingLine = false;
    uint32_t lastByteAt = 0;
    bool ledState = false;
    uint32_t lastHeartbeatAt = 0;
};
static SystemState state;

// Hardware Control
void setLed(bool ison){
    const bool outputHigh = LED_ACTIVE_HIGH ? ison : !ison;
    digitalWrite(LED_PIN, outputHigh ? HIGH : LOW);
    state.ledState = ison;
}

// Command Handlers
void ping(){
    state.lastHeartbeatAt = millis();
    Serial.println("PONG");
}
void LedOn(){
    if (!state.ledState){
        setLed(true);
        state.lastHeartbeatAt = millis();
    }
    Serial.println("ACK:LED_ON");
}

void LedOff(){
    setLed(false);
    Serial.println("ACK:LED_OFF");
}

void Status(){
    Serial.println(state.ledState ? "STATUS:LED_ON" : "STATUS:LED_OFF");
}

void Version(){
    Serial.print("VERSION:FW=");
    Serial.println(FW_VERSION);
}

// Command Table
class Command{
public:
    const char* name;
    void (*handler)();
};

const Command COMMANDS[] = {
    { "PING",    ping    },
    { "LED_ON",  LedOn   },
    { "LED_OFF", LedOff  },
    { "STATUS",  Status  },
    { "VERSION", Version }
};

constexpr size_t COMMAND_COUNT =
    sizeof(COMMANDS) / sizeof(COMMANDS[0]);

// Command Normalization
// Trims spaces and tabs.Converts lower to upper case.

char* normalizeCommand(char* text){
    // Remove whitespace.
    while (*text == ' ' || *text == '\t'){
        text++;
    }
    size_t length = strlen(text);
    while (length > 0 && (text[length - 1] == ' ' || text[length - 1] == '\t')){
        text[--length] = '\0';
    }
    // Convert ASCII lowercase letters to uppercase.
    for (size_t i = 0; i < length; i++){
        if (text[i] >= 'a' && text[i] <= 'z'){
            text[i] = static_cast<char>(text[i] - 'a' + 'A');
        }
    }
    return text;
}

// Command Processing
void processCommand(char* rawCommand){
    char* command = normalizeCommand(rawCommand);
    // Ignore empty commands.
    if (command[0] == '\0'){
        return;
    }
    // Find a matching command.
    for (size_t i = 0; i < COMMAND_COUNT; i++){
        if (strcmp(command, COMMANDS[i].name) == 0){
            COMMANDS[i].handler();
            return;
        }
    }
    Serial.println("ERR:UNKNOWN_COMMAND");
}

// Receiver Reset
void resetReceiver(){
    state.commandLength = 0;
    state.discardingLine = false;
}

// Serial Command Receiver
void receiveSerialCommands(){
    while (Serial.available() > 0){
        const int raw = Serial.read();
        if (raw < 0){
            break;
        }
        const char incoming = static_cast<char>(raw);
        if (incoming == '\r'){
            continue;
        }
        if (incoming == '\n'){
            if (state.discardingLine){
                resetReceiver();
            }
            else{
                state.commandBuffer[state.commandLength] = '\0';
                processCommand(state.commandBuffer);
                state.commandLength = 0;
            }
            continue;
        }
        state.lastByteAt = millis();
        if (state.discardingLine){
            continue;
        }
        if ((raw < 32 && raw != '\t') || raw > 126){
            state.commandLength = 0;
            state.discardingLine = true;
            Serial.println("ERR:INVALID_CHAR");
            continue;
        }
        // Reserve one byte for the null terminator.
        if (state.commandLength < BUFFER_SIZE - 1){
            state.commandBuffer[state.commandLength++] = incoming;
        }
        else{
            state.commandLength = 0;
            state.discardingLine = true;
            Serial.println("ERR:LINE_TOO_LONG");
        }
    }
    // Discard an incomplete line if no more bytes arrive.
    if ((state.commandLength > 0 || state.discardingLine) && (millis() - state.lastByteAt >= COMMAND_TIMEOUT_MS)){
        const bool hadIncompleteCommand = state.commandLength > 0;
        resetReceiver();
        if (hadIncompleteCommand){
            Serial.println("ERR:TIMEOUT");
        }
    }
}
// Turns Off led if no response from computer
void checkFailsafe(){
    if (FAILSAFE_TIMEOUT_MS == 0){
        return;
    }
    if (!state.ledState){
        return;
    }
    if (millis() - state.lastHeartbeatAt >= FAILSAFE_TIMEOUT_MS){
        setLed(false);
        Serial.println("EVT:FAILSAFE_LED_OFF");
    }
}
void setup(){
    const bool offLevelHigh = !LED_ACTIVE_HIGH;
    digitalWrite(LED_PIN,offLevelHigh ? HIGH : LOW);
    pinMode(LED_PIN, OUTPUT);
    state.ledState = false;
    Serial.begin(SERIAL_BAUD_RATE);
    state.lastByteAt = millis();
    state.lastHeartbeatAt = millis();
    Serial.println("READY");
}
void loop(){
    receiveSerialCommands();
    checkFailsafe();
}