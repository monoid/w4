function Chat(id) {
    this.el = $('#'+id);
}

Chat.prototype.message = function (obj) {
    var ts = new Date(obj.ts)
    var msg = $('<div>')
        .append($('<span class="ts">').text('['+ts.getHours()+':'+ts.getMinutes()+'] '));
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
        // Do nothing
        break;

        case 'me':
        msg.append($('<span class="me">').text(obj.user+" "+obj.message));
        break;

        case 'sysmsg':
        msg.append($('<span class="sysmsg">').text(obj.message));
        break;
    }
    msg.appendTo(this.el);
};


function login(username) {
    $.ajax({ url: '/ajax/login',
             data: { 'name': username },
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
}

function message(msg) {
    $.ajax({ url: '/ajax/post',
             data: { 'message': msg },
             type: 'POST'
           });
}   

(function poll(){
    $.ajax({ url: "/ajax/poll", success: function(data){
        for (var i in data) {
            chat.message(data[i]);
        }
    }, dataType: "json", complete: poll, timeout: 30000 });
})();


var chat;

$(document).ready(function () {
    chat = new Chat("chat");

    $('#loginbtn').click(function () {
        if ($('#username').val()) {
            login($('#username').val());
            $('#login').hide();

            $("#inputline").attr('disabled', null);
            $("#sendbtn").attr('disabled', null);

            $("#chat").show();
            $("#input").show();

            $("#sendbtn").click(function () {
                message($("#inputline").val());
                $("#inputline").val('').focus();
            });

            $('#inputline').keyup(function (evt) {
                if (evt.keyCode == 13) {
                    $('#sendbtn').click();
                }
            });
        }
    });
});
