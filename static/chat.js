var TIMEOUT = 180000; // 3 minutes
var ERR_TIMEOUT = 60000; // 1 minute

function hourfmt(ts) {
    var h = ('0'+ts.getHours()).slice(-2);
    var m = ('0'+ts.getMinutes()).slice(-2);
    return h+':'+m;
}

var InputWin = Backbone.View.extend({
    events: {
        'click #sendbtn': 'sendMessage',
        'keyup #inputline': 'checkEnter'
    },
    show: function () {
        $("#inputline").attr('disabled', null);
        $("#sendbtn").attr('disabled', null);
        this.$el.show();
    },
    disable: function () {
        $("#inputline").attr('disabled', 'disabled');
        $("#sendbtn").attr('disabled', 'disabled');
    },
    checkEnter: function (evt) {
        if (evt.ctrlKey && (evt.keyCode == 13 || evt.keyCode == 10)) {
            $('#sendbtn').click();
        }
    },
    sendMessage: function () {
        var msg = $("#inputline").val();
        $.ajax({ url: '/ajax/post',
                 data: { 'message': msg, 'group': this.options.group },
                 type: 'POST'
               });
        $("#inputline").val('').focus();
    },
    clickNick: function (nick) {
        $('#inputline').val($('#inputline').val() + nick + ': ');
    }
});

var ChatWindow = Backbone.View.extend({
    prevTs: null,

    events: {
        'click .nick': 'clickNick'
    },

    show: function () {
            this.$el.show();
    },
    message: function (obj) {
        var dayChanged = !this.prevTs;
        var ts = new Date(obj.ts)

        if (this.prevTs) {
            if (ts.getDate() != this.prevTs.getDate()
                || ts.getMonth() != this.prevTs.getMonth()
                || ts.getFullYear() != this.prevTs.getFullYear()) {
               dayChanged = true;
            }
        }

        if (obj.ts) this.prevTs = ts;

        if (dayChanged && obj.ts) {
            var dt = $('<div>').addClass('daychange');
            dt.html("&mdash; "+ts.toDateString()+" &mdash;");
            dt.appendTo(this.$el);
        }

        var msg = $('<div>');
        if (obj.cmd != 'subject' && obj.cmd != 'error' && obj.cmd != 'bye') {
            msg.append($('<span class="ts">').text('['+hourfmt(ts)+'] '));
        }
        switch (obj.cmd) {
        case 'say':
            if (obj.message.startsWith('/me ')) {
                msg.append($('<span class="me">').text(obj.user+" "+obj.message.substr(4)));
            } else {
                msg.append($('<span class="nick">').text(obj.user+": "),
                           $('<span class="say">').text(obj.message));
            }
            break;

        case 'join':
            msg.append($('<span>').addClass(obj.cmd)
                       .text(obj.user+" joins."));

            this.options.rosterwin.addUser(obj.user);
            break;

        case 'leave':
            msg.append($('<span>').addClass(obj.cmd)
                       .text(obj.user+" leaves."));
            this.options.rosterwin.delUser(obj.user);
            break;

        case 'ping':
            // Do nothing, do not even insert message
            return;

        case 'me':
            msg.append($('<span class="me">').text(obj.user+" "+obj.message));
            break;

        case 'sysmsg':
            msg.append($('<span class="sysmsg">').text(obj.message));
            break;

        case 'subject':
            msg.addClass('subject').append($('<span class="subject">').text("Subject: "+obj.message));
            break;

        case 'error':
            msg.append($('<span class="error">').text("Error: "+obj.message));
            this.options.inputwin.disable();
            break;

        case 'bye':
            msg.append($('<span class="bye error">').text("Bye-bye."));
            this.options.inputwin.disable();
            break;
        }
        msg.appendTo(this.$el);
    },

    clickNick: function (evt) {
        var nick = $(evt.target).text();
        // Trim ": " at end
        nick = nick.substr(0, nick.length-2);
        this.options.inputwin.clickNick(nick);
    }
});

var Roster = Backbone.View.extend({
    events: {
        'click .nick': 'clickNick'
    },

    addUser: function (nick) {
        var rosterList = $(this.el);
        rosterList.append($('<li class="nick">').text(nick));
    },

    delUser: function (nick) {
        this.$('li').filter(function (li) {
            return ($(this).text() == nick);
        }).eq(0).remove();
    },

    clickNick: function (evt) {
        var nick = $(evt.target).text();
        this.options.inputwin.clickNick(nick);
    }
});

var LoginWindow = Backbone.View.extend({
    el: $('#login'),
    events: {
        'click #loginbtn': 'login'
    },
    
    login: function () {
        var username = $('#username').val().trim();
        var self = this;
        if (username) {
            $.ajax({ url: '/ajax/login',
                     data: { 'name': username, group: this.options.group },
                     dataType: 'json',
                     type: 'POST',
                     success: function (data) {
                         for (var i in data.users) {
                             self.options.rosterwin.addUser(data.users[i]);
                         }
                     }
                   });
            this.$el.hide();
            this.options.logoutwin.show();
            this.options.chatwin.show();
            this.options.inputwin.show();
        }

    }
});

var LogoutWindow = Backbone.View.extend({
    events: {
        'click #logoutbtn': 'logout'
    },

    show: function () {
        this.$el.show();
        this.$("#logoutbtn").attr('disabled', null);
    },
    logout: function () {
        this.options.inputwin.disable();
        $.ajax({
            url: '/ajax/logout',
            type: 'POST',
            success: function () {
                aj.abort();
                location.href = '.';
            }
        });
    }
});

var aj;
function poll(){
    aj = $.ajax({ url: "/ajax/poll", success: function(data){
        for (var i in data) {
            chatwin.message(data[i]);
        }
        poll();
    }, dataType: "json",
       timeout: TIMEOUT,
       type: 'POST',
       error: function () {
           // TODO inform user
           setTimeout(poll, ERR_TIMEOUT);
       }
    });
}


var chatwin;
var login;
var inputwin;

$(document).ready(function () {
    inputwin = new InputWin({el: '#input', group: 'test'});
    var rosterwin = new Roster({el: '#roster-list',
                                inputwin: inputwin
                               });
    chatwin = new ChatWindow({
        el: '#chat',
        group: 'test',
        inputwin: inputwin,
        rosterwin: rosterwin
    });
    var logoutwin = new LogoutWindow({
        el: '#logout',
        inputwin: inputwin
    });
    login = new LoginWindow({
        el: '#login',
        chatwin: chatwin,
        inputwin: inputwin,
        logoutwin: logoutwin,
        rosterwin: rosterwin,
        group: 'test'
    });
    poll();
});
