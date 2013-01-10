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
    }
});

var ChatWindow = Backbone.View.extend({
    show: function () {
            this.$el.show();
    },
    message: function (obj) {
        var ts = new Date(obj.ts)
        var msg = $('<div>')
        if (obj.cmd != 'subject') {
            msg.append($('<span class="ts">').text('['+hourfmt(ts)+'] '));
        }
        switch (obj.cmd) {
        case 'say':
            msg.append($('<span class="nick">').text(obj.user+": "),
                       $('<span class="say">').text(obj.message));
            break;

        case 'join':
            msg.append($('<span>').addClass(obj.cmd)
                       .text(obj.user+" joins."));

            $('#roster-list').append($("<li>").text(obj.user));
            break;

        case 'leave':
            msg.append($('<span>').addClass(obj.cmd)
                       .text(obj.user+" leaves."));
            $('#roster-list>li').filter(function (li) {
                return ($(this).text() == obj.user);
            }).eq(0).remove();
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
            msg.append($('<span class="subject">').text("Subject: "+obj.message));
        }
        msg.appendTo(this.$el);
    }
});

var LoginWindow = Backbone.View.extend({
    el: $('#login'),
    events: {
        'click #loginbtn': 'login'
    },
    
    login: function () {
        var username = $('#username').val().trim();
        if (username) {
            $.ajax({ url: '/ajax/login',
                     data: { 'name': username, group: this.options.group },
                     dataType: 'json',
                     type: 'POST',
                     success: function (data) {
                         // TODO: dedicated class for roster that handles duplicated
                         // entries
                         var rosterList = $('#roster-list');
                         for (var i in data.users) {
                             rosterList.append($("<li>").text(data.users[i]));
                         }
                     }
                   });
            this.$el.hide();

            this.options.chatwin.show();
            this.options.inputwin.show();
        }

    }
});


(function poll(){
    $.ajax({ url: "/ajax/poll", success: function(data){
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
})();


var chatwin;
var login;
var inputwin;

$(document).ready(function () {
    chatwin = new ChatWindow({el: '#chat', group: 'test'});
    inputwin = new InputWin({el: '#input', group: 'test'});
    login = new LoginWindow({el: '#login',
                             chatwin: chatwin,
                             inputwin: inputwin,
                             group: 'test'});
});
