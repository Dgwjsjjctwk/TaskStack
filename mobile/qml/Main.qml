import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 360
    height: 720
    title: "TaskStack"
    color: "#0d1117"

    Material.theme: Material.Dark
    Material.accent: "#388bfd"
    Material.primary: "#161b22"
    Material.background: "#0d1117"

    readonly property color cardColor: "#161b22"
    readonly property color borderColor: "#30363d"
    readonly property color mutedColor: "#8b949e"
    readonly property var priorityColors: ["#f85149", "#d29922", "#3fb950"]

    // Selection made in the share dialog, used when a task is added.
    property var selectedUsers: []
    property var selectedGroups: []
    property string statusFilter: "all"

    // Reading backend.language makes every binding that calls txt() re-evaluate
    // when the language changes.
    function txt(key) {
        var lang = backend.language
        return backend.tr(key)
    }

    function fill(text, values) {
        var result = text
        for (var name in values)
            result = result.replace("{" + name + "}", values[name])
        return result
    }

    function toggled(list, id, on) {
        var copy = list.filter(function (x) { return x !== id })
        if (on)
            copy.push(id)
        return copy
    }

    function applyFilter() {
        var category = categoryFilter.currentIndex > 0 ? categoryFilter.currentText : ""
        backend.setFilter(statusFilter, searchField.text, category)
    }

    function showToast(text, isError) {
        toastLabel.text = text
        toast.isError = isError
        toast.opacity = 1
        toastTimer.restart()
    }

    Connections {
        target: backend
        function onMessage(text, isError) { window.showToast(text, isError) }
        function onTaskAdded() { addPopup.close() }
        function onRegistered() { loginPage.registerMode = false }
        function onLoggedInChanged() {
            if (!backend.loggedIn) {
                window.selectedUsers = []
                window.selectedGroups = []
            }
        }
        function onLanguageChanged() { Qt.callLater(window.applyFilter) }
    }

    // ------------------------------------------------------------------
    // Pages
    // ------------------------------------------------------------------

    StackLayout {
        anchors.fill: parent
        currentIndex: backend.loggedIn ? 1 : 0

        // -------------------------- Login ------------------------------
        Item {
            id: loginPage
            property bool registerMode: false

            Flickable {
                anchors.fill: parent
                contentHeight: loginColumn.implicitHeight + 64
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: loginColumn
                    width: parent.width - 48
                    x: 24
                    y: 48
                    spacing: 14

                    Label {
                        text: "✓"
                        font.pixelSize: 56
                        color: "#388bfd"
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Label {
                        text: "TaskStack"
                        font.pixelSize: 26
                        font.bold: true
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Label {
                        text: loginPage.registerMode ? txt("register_title") : txt("login_title")
                        color: window.mutedColor
                        Layout.alignment: Qt.AlignHCenter
                    }

                    TextField {
                        id: userField
                        Layout.fillWidth: true
                        placeholderText: txt("username")
                        inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
                        onAccepted: passField.forceActiveFocus()
                    }
                    TextField {
                        id: passField
                        Layout.fillWidth: true
                        placeholderText: txt("password")
                        echoMode: TextInput.Password
                        onAccepted: submit.clicked()
                    }
                    Button {
                        id: submit
                        Layout.fillWidth: true
                        highlighted: true
                        enabled: !backend.busy
                        text: loginPage.registerMode ? txt("sign_up") : txt("sign_in")
                        onClicked: {
                            if (loginPage.registerMode)
                                backend.register(userField.text, passField.text)
                            else
                                backend.login(userField.text, passField.text)
                        }
                    }
                    Button {
                        Layout.fillWidth: true
                        flat: true
                        text: loginPage.registerMode ? txt("have_account") : txt("no_account")
                        onClicked: loginPage.registerMode = !loginPage.registerMode
                    }
                    Button {
                        Layout.fillWidth: true
                        flat: true
                        text: txt("settings")
                        onClicked: settingsPopup.open()
                    }
                    BusyIndicator {
                        running: backend.busy
                        visible: backend.busy
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
        }

        // -------------------------- Tasks ------------------------------
        Item {
            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Header
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 56
                    color: "#161b22"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 4
                        spacing: 8

                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            color: backend.online ? "#3fb950" : "#f85149"
                        }
                        Label {
                            text: backend.username
                            font.pixelSize: 18
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        ToolButton {
                            text: txt("refresh")
                            font.pixelSize: 13
                            onClicked: backend.refresh()
                        }
                        ToolButton {
                            text: txt("settings")
                            font.pixelSize: 13
                            onClicked: settingsPopup.open()
                        }
                    }
                }
                ProgressBar {
                    Layout.fillWidth: true
                    from: 0
                    to: 100
                    value: backend.stats.percent === undefined ? 0 : backend.stats.percent
                    padding: 0
                    visible: backend.busy || backend.stats.total > 0
                    indeterminate: backend.busy
                }

                // Statistics
                Label {
                    Layout.fillWidth: true
                    Layout.leftMargin: 16
                    Layout.rightMargin: 16
                    Layout.topMargin: 10
                    color: window.mutedColor
                    font.pixelSize: 13
                    text: {
                        var s = backend.stats
                        if (s.total === undefined)
                            return ""
                        var line = fill(txt("stats"), { done: s.done, total: s.total })
                        if (s.overdue > 0)
                            line += "  ·  " + fill(txt("overdue"), { n: s.overdue })
                        return line
                    }
                }

                // Search and filters
                TextField {
                    id: searchField
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    placeholderText: txt("search")
                    inputMethodHints: Qt.ImhNoPredictiveText
                    onTextChanged: window.applyFilter()
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    spacing: 6

                    Repeater {
                        model: [
                            { key: "all", label: "filter_all" },
                            { key: "active", label: "filter_active" },
                            { key: "completed", label: "filter_done" }
                        ]
                        delegate: Button {
                            required property var modelData
                            Layout.fillWidth: true
                            flat: window.statusFilter !== modelData.key
                            highlighted: window.statusFilter === modelData.key
                            text: txt(modelData.label)
                            font.pixelSize: 12
                            onClicked: {
                                window.statusFilter = modelData.key
                                window.applyFilter()
                            }
                        }
                    }
                }
                ComboBox {
                    id: categoryFilter
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    model: [txt("all_categories")].concat(backend.categoryChoices)
                    onActivated: window.applyFilter()
                }

                // Task list
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.topMargin: 6

                Label {
                    anchors.centerIn: parent
                    visible: taskList.count === 0 && !backend.busy
                    color: window.mutedColor
                    text: backend.stats.total > 0 ? txt("empty_filtered") : txt("empty_list")
                }
                Timer {
                    id: pullTimer
                    interval: 400
                    onTriggered: backend.refresh()
                }

                ListView {
                    id: taskList
                    anchors.fill: parent
                    clip: true
                    spacing: 8
                    leftMargin: 12
                    rightMargin: 12
                    topMargin: 4
                    bottomMargin: 88
                    model: backend.tasks
                    boundsBehavior: Flickable.DragOverBounds

                    // Pull down to refresh.
                    onContentYChanged: {
                        if (contentY < -90 && !backend.busy && dragging)
                            pullTimer.restart()
                    }

                    delegate: Rectangle {
                        id: card
                        required property var modelData
                        width: taskList.width - taskList.leftMargin - taskList.rightMargin
                        implicitHeight: cardRow.implicitHeight + 20
                        radius: 10
                        color: window.cardColor
                        border.color: modelData.overdue ? "#f85149" : window.borderColor
                        border.width: 1
                        opacity: modelData.completed ? 0.55 : 1

                        Rectangle {
                            width: 4
                            height: parent.height - 16
                            radius: 2
                            anchors.left: parent.left
                            anchors.leftMargin: 6
                            anchors.verticalCenter: parent.verticalCenter
                            color: window.priorityColors[modelData.priorityRank]
                        }

                        RowLayout {
                            id: cardRow
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 14
                            anchors.rightMargin: 4
                            spacing: 4

                            CheckBox {
                                checked: card.modelData.completed
                                onToggled: backend.toggleTask(card.modelData.id, checked)
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3

                                Label {
                                    Layout.fillWidth: true
                                    text: card.modelData.title
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 16
                                    font.strikeout: card.modelData.completed
                                }
                                Label {
                                    Layout.fillWidth: true
                                    wrapMode: Text.Wrap
                                    font.pixelSize: 12
                                    color: window.mutedColor
                                    text: card.modelData.category + "  ·  " + card.modelData.priority
                                }
                                Label {
                                    visible: card.modelData.deadline !== ""
                                    Layout.fillWidth: true
                                    font.pixelSize: 12
                                    color: card.modelData.overdue ? "#f85149" : window.mutedColor
                                    text: txt("deadline") + ": " + card.modelData.deadline
                                }
                                Label {
                                    visible: card.modelData.author !== "" || card.modelData.shared
                                    Layout.fillWidth: true
                                    font.pixelSize: 12
                                    color: "#58a6ff"
                                    text: {
                                        var parts = []
                                        if (card.modelData.author !== "")
                                            parts.push(fill(txt("from_author"), { name: card.modelData.author }))
                                        if (card.modelData.shared)
                                            parts.push(txt("shared_badge"))
                                        return parts.join("  ·  ")
                                    }
                                }
                            }
                            ToolButton {
                                text: "×"
                                font.pixelSize: 28
                                onClicked: {
                                    deletePopup.taskId = card.modelData.id
                                    deletePopup.taskTitle = card.modelData.title
                                    deletePopup.open()
                                }
                            }
                        }
                    }
                }
                }
            }

            RoundButton {
                id: fab
                text: "+"
                font.pixelSize: 30
                highlighted: true
                width: 60
                height: 60
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 18
                onClicked: {
                    titleField.text = ""
                    deadlineField.text = ""
                    window.selectedUsers = []
                    window.selectedGroups = []
                    categoryBox.currentIndex = 0
                    priorityBox.currentIndex = 0
                    addPopup.open()
                    titleField.forceActiveFocus()
                }
            }
        }
    }

    // ------------------------------------------------------------------
    // Popups
    // ------------------------------------------------------------------

    Popup {
        id: addPopup
        parent: Overlay.overlay
        modal: true
        focus: true
        x: (window.width - width) / 2
        y: Math.max(8, (window.height - height) / 4)
        width: Math.min(window.width - 24, 480)
        padding: 16
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        ColumnLayout {
            width: parent.width
            spacing: 10

            Label {
                text: txt("new_task")
                font.pixelSize: 20
                font.bold: true
            }
            TextField {
                id: titleField
                Layout.fillWidth: true
                placeholderText: txt("task_title_hint")
                inputMethodHints: Qt.ImhNoPredictiveText
            }
            Label { text: txt("category"); color: window.mutedColor; font.pixelSize: 12 }
            ComboBox {
                id: categoryBox
                Layout.fillWidth: true
                model: backend.categoryChoices
            }
            Label { text: txt("priority"); color: window.mutedColor; font.pixelSize: 12 }
            ComboBox {
                id: priorityBox
                Layout.fillWidth: true
                model: backend.priorityChoices
            }
            Label { text: txt("deadline"); color: window.mutedColor; font.pixelSize: 12 }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Repeater {
                    model: [
                        { key: "none", label: "dl_none" },
                        { key: "today", label: "dl_today" },
                        { key: "tomorrow", label: "dl_tomorrow" },
                        { key: "week", label: "dl_week" }
                    ]
                    delegate: Button {
                        required property var modelData
                        flat: true
                        text: txt(modelData.label)
                        font.pixelSize: 12
                        onClicked: deadlineField.text = backend.quickDeadline(modelData.key)
                    }
                }
            }
            TextField {
                id: deadlineField
                Layout.fillWidth: true
                placeholderText: txt("deadline_hint")
                inputMethodHints: Qt.ImhDigitsOnly | Qt.ImhNoPredictiveText
            }
            Button {
                Layout.fillWidth: true
                text: (window.selectedUsers.length + window.selectedGroups.length) > 0
                      ? fill(txt("share_selected"), { n: window.selectedUsers.length + window.selectedGroups.length })
                      : txt("share")
                highlighted: (window.selectedUsers.length + window.selectedGroups.length) > 0
                onClicked: {
                    backend.loadSharing()
                    sharePopup.open()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    Layout.fillWidth: true
                    text: txt("cancel")
                    flat: true
                    onClicked: addPopup.close()
                }
                Button {
                    Layout.fillWidth: true
                    text: txt("add")
                    highlighted: true
                    enabled: !backend.busy
                    onClicked: backend.addTask(
                        titleField.text,
                        priorityBox.currentText,
                        categoryBox.currentText,
                        deadlineField.text,
                        window.selectedUsers,
                        window.selectedGroups)
                }
            }
        }
    }

    Popup {
        id: sharePopup
        parent: Overlay.overlay
        modal: true
        x: (window.width - width) / 2
        y: Math.max(8, (window.height - height) / 6)
        width: Math.min(window.width - 24, 480)
        height: Math.min(window.height - 48, 560)
        padding: 16
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        ColumnLayout {
            anchors.fill: parent
            spacing: 8

            Label {
                text: txt("share_title")
                font.pixelSize: 20
                font.bold: true
            }
            Flickable {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentHeight: shareColumn.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: shareColumn
                    width: parent.width
                    spacing: 0

                    Label {
                        text: txt("share_users")
                        color: window.mutedColor
                        font.pixelSize: 12
                    }
                    Label {
                        visible: backend.users.length === 0
                        text: txt("share_empty")
                        color: window.mutedColor
                        topPadding: 8
                        bottomPadding: 8
                    }
                    Repeater {
                        model: backend.users
                        delegate: CheckBox {
                            required property var modelData
                            Layout.fillWidth: true
                            text: modelData.username
                            checked: window.selectedUsers.indexOf(modelData.id) >= 0
                            onToggled: window.selectedUsers = window.toggled(window.selectedUsers, modelData.id, checked)
                        }
                    }
                    Label {
                        visible: backend.groups.length > 0
                        text: txt("share_groups")
                        color: window.mutedColor
                        font.pixelSize: 12
                        topPadding: 10
                    }
                    Repeater {
                        model: backend.groups
                        delegate: CheckBox {
                            required property var modelData
                            Layout.fillWidth: true
                            text: modelData.name
                            checked: window.selectedGroups.indexOf(modelData.id) >= 0
                            onToggled: window.selectedGroups = window.toggled(window.selectedGroups, modelData.id, checked)
                        }
                    }
                    TextField {
                        id: groupNameField
                        Layout.fillWidth: true
                        Layout.topMargin: 12
                        placeholderText: txt("group_name")
                    }
                    Button {
                        Layout.fillWidth: true
                        flat: true
                        text: txt("create_group")
                        enabled: !backend.busy
                        onClicked: backend.createGroup(groupNameField.text, window.selectedUsers)
                    }
                }
            }
            Button {
                Layout.fillWidth: true
                text: txt("done")
                highlighted: true
                onClicked: sharePopup.close()
            }
        }

        Connections {
            target: backend
            function onGroupCreated() { groupNameField.text = "" }
        }
    }

    Popup {
        id: deletePopup
        property int taskId: -1
        property string taskTitle: ""
        parent: Overlay.overlay
        modal: true
        x: (window.width - width) / 2
        y: (window.height - height) / 3
        width: Math.min(window.width - 40, 420)
        padding: 16
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        ColumnLayout {
            width: parent.width
            spacing: 12
            Label {
                text: txt("delete_title")
                font.pixelSize: 20
                font.bold: true
            }
            Label {
                Layout.fillWidth: true
                text: deletePopup.taskTitle
                wrapMode: Text.Wrap
                color: window.mutedColor
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Button {
                    Layout.fillWidth: true
                    flat: true
                    text: txt("cancel")
                    onClicked: deletePopup.close()
                }
                Button {
                    Layout.fillWidth: true
                    text: txt("delete")
                    Material.background: "#da3633"
                    Material.foreground: "white"
                    onClicked: {
                        backend.deleteTask(deletePopup.taskId)
                        deletePopup.close()
                    }
                }
            }
        }
    }

    Popup {
        id: settingsPopup
        parent: Overlay.overlay
        modal: true
        x: (window.width - width) / 2
        y: Math.max(8, (window.height - height) / 4)
        width: Math.min(window.width - 24, 480)
        padding: 16
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onAboutToShow: serverField.text = backend.serverUrl

        ColumnLayout {
            width: parent.width
            spacing: 10

            Label {
                text: txt("settings")
                font.pixelSize: 20
                font.bold: true
            }
            Label { text: txt("language"); color: window.mutedColor; font.pixelSize: 12 }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Button {
                    Layout.fillWidth: true
                    text: "Русский"
                    highlighted: backend.language === "ru"
                    flat: backend.language !== "ru"
                    onClicked: backend.setLanguage("ru")
                }
                Button {
                    Layout.fillWidth: true
                    text: "English"
                    highlighted: backend.language === "en"
                    flat: backend.language !== "en"
                    onClicked: backend.setLanguage("en")
                }
            }
            Label { text: txt("server"); color: window.mutedColor; font.pixelSize: 12 }
            TextField {
                id: serverField
                Layout.fillWidth: true
                inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoPredictiveText
                onAccepted: backend.setServerUrl(text)
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Button {
                    Layout.fillWidth: true
                    flat: true
                    text: txt("server_reset")
                    onClicked: {
                        serverField.text = backend.defaultServerUrl
                        backend.setServerUrl(serverField.text)
                    }
                }
                Button {
                    Layout.fillWidth: true
                    text: txt("done")
                    highlighted: true
                    onClicked: {
                        backend.setServerUrl(serverField.text)
                        settingsPopup.close()
                    }
                }
            }
            Label {
                Layout.fillWidth: true
                font.pixelSize: 12
                color: backend.online ? "#3fb950" : "#f85149"
                text: backend.online ? txt("online") : txt("offline")
            }
            Button {
                Layout.fillWidth: true
                visible: backend.loggedIn
                flat: true
                text: txt("sign_out")
                Material.foreground: "#f85149"
                onClicked: {
                    settingsPopup.close()
                    backend.logout()
                }
            }
            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: 11
                color: window.mutedColor
                text: fill(txt("version"), { v: backend.version })
            }
        }
    }

    // ------------------------------------------------------------------
    // Toast
    // ------------------------------------------------------------------

    Rectangle {
        id: toast
        property bool isError: true
        parent: Overlay.overlay
        z: 100
        opacity: 0
        radius: 10
        color: isError ? "#da3633" : "#238636"
        width: Math.min(parent.width - 32, toastLabel.implicitWidth + 32)
        height: toastLabel.implicitHeight + 24
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 96
        visible: opacity > 0

        Behavior on opacity { NumberAnimation { duration: 200 } }

        Label {
            id: toastLabel
            anchors.centerIn: parent
            width: parent.width - 32
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
            color: "white"
        }
        MouseArea {
            anchors.fill: parent
            onClicked: toast.opacity = 0
        }
    }
    Timer {
        id: toastTimer
        interval: 3500
        onTriggered: toast.opacity = 0
    }
}
